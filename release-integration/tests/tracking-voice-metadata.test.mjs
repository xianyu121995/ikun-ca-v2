import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveTrackingVoiceMetadata} from '../../apps/website/lib/tracking-voice-metadata.ts';
const subscription_id='sub_11111111-1111-4111-8111-111111111111',project_id='prj_22222222-2222-4222-8222-222222222222';
const candidate={subscription_id,project_id};
const sub=()=>({subscription_id,project_id,notes:'真实订阅备注',revision:2,name:'不得播报的名称'});
const project=()=>({project_id,revision:3,rating:'A'});
const ok=data=>Response.json({data,request_id:'voice_test'});
const context=()=>({user_id:'usr_fixture',epoch:'page_fixture',role:'user',signal:new AbortController().signal});
function setup(responses){const requests=[];let revocations=0;const resolve=resolveTrackingVoiceMetadata(()=>revocations++,async(path,init)=>{requests.push({path,init});return responses.shift();});return {resolve,requests,revocations:()=>revocations};}
test('uses only the two real resource IDs and current notes/rating/revisions',async()=>{
 const s=setup([ok(sub()),ok(project())]);const result=await s.resolve(candidate,context());
 assert.deepEqual(result,{subscription_id,project_id,notes:'真实订阅备注',subscription_revision:2,rating:'A',project_revision:3});
 assert.deepEqual(s.requests.map(x=>x.path),['/api/v1/tracking/subscriptions/'+subscription_id,'/api/v1/projects/'+project_id]);
 assert.ok(s.requests.every(x=>x.init.credentials==='same-origin'&&x.init.cache==='no-store'&&x.init.redirect==='error'&&x.init.signal));
});
test('401 from subscription immediately revokes without reading a project',async()=>{const s=setup([new Response('{}',{status:401})]);assert.equal(await s.resolve(candidate,context()),null);assert.equal(s.revocations(),1);assert.equal(s.requests.length,1);});
test('401 from Projects revokes and returns no metadata',async()=>{const s=setup([ok(sub()),new Response('{}',{status:401})]);assert.equal(await s.resolve(candidate,context()),null);assert.equal(s.revocations(),1);});
test('non-success is not metadata and does not revoke an otherwise valid identity',async()=>{for(const status of [403,404,429,500,503]){const s=setup([new Response('{}',{status})]);assert.equal(await s.resolve(candidate,context()),null);assert.equal(s.revocations(),0);}});
test('strict successful transport envelope and request ID are mandatory',async()=>{for(const value of [{data:sub()},{data:sub(),request_id:''},{data:sub(),request_id:'voice_test',error:{}},{data:sub(),request_id:'bad request'},{data:[],request_id:'voice_test'}]){const s=setup([Response.json(value)]);assert.equal(await s.resolve(candidate,context()),null);assert.equal(s.requests.length,1);}});
test('subscription identity, canonical reference and positive safe revision cannot be substituted',async()=>{for(const patch of [{subscription_id:'sub_wrong'},{project_id:'prj_wrong'},{revision:0},{revision:true},{revision:9007199254740992}]){const s=setup([ok({...sub(),...patch})]);assert.equal(await s.resolve(candidate,context()),null);assert.equal(s.requests.length,1);}});
test('blank or absent notes never fall back to name or event data',async()=>{for(const notes of ['', '   ',null,undefined,'x'.repeat(4001)]){const s=setup([ok({...sub(),notes})]);assert.equal(await s.resolve({...candidate,notes:'伪造事件备注'},context()),null);assert.equal(s.requests.length,1);}});
test('only canonical Projects S/A/B and a positive revision qualify',async()=>{for(const patch of [{rating:'C'},{rating:'D'},{rating:null},{rating:'s'},{revision:-1},{revision:'3'},{project_id:'prj_other'}]){const s=setup([ok(sub()),ok({...project(),...patch})]);assert.equal(await s.resolve(candidate,context()),null);}});
test('caller abort stops metadata before any subsequent lookup',async()=>{const ctx=context(),abort=new AbortController();ctx.signal=abort.signal;const s=setup([ok(sub()),ok(project())]);abort.abort();assert.equal(await s.resolve(candidate,ctx),null);assert.equal(s.requests.length,1);});
test('single request budget aborts at two seconds without returning partial metadata',async()=>{let aborted=false;const resolve=resolveTrackingVoiceMetadata(()=>{},(_path,{signal})=>new Promise((_,reject)=>{signal.addEventListener('abort',()=>{aborted=true;reject(new Error('aborted'));},{once:true});}));const start=Date.now();assert.equal(await resolve(candidate,context()),null);assert.ok(aborted);assert.ok(Date.now()-start<2500);});
test('oversized response cancels its reader and never reaches Projects',async()=>{let canceled=false;const body=new ReadableStream({pull(c){c.enqueue(new Uint8Array(32769));},cancel(){canceled=true;}});const s=setup([new Response(body,{headers:{'content-type':'application/json'}})]);assert.equal(await s.resolve(candidate,context()),null);assert.ok(canceled);assert.equal(s.requests.length,1);});
test('invalid JSON or content type cannot supply voice metadata',async()=>{for(const response of [new Response('not json',{headers:{'content-type':'application/json'}}),new Response('{}',{headers:{'content-type':'text/html'}})]){const s=setup([response]);assert.equal(await s.resolve(candidate,context()),null);}});
