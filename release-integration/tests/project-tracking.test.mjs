import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {fixture,req,user} from '../../modules/auth/tests/helpers.mjs';
import {projectTrackingRoute} from '../../apps/website/lib/project-tracking.ts';
import {existingTracking,existingTrackingMessage,normalizeXHandle} from '../../apps/website/lib/project-tracking-model.ts';
const pid='prj_'+randomUUID(),other='prj_'+randomUUID(),sid='sub_'+randomUUID(),path='/api/v1/tracking/project-entry?project_id='+pid;
const ok=data=>Response.json({data,request_id:'fixture'});
const entry=(overrides={})=>({subscription_id:sid,project_id:pid,x_handle:'example',desired_state:'running',...overrides});
async function run(fn){await fixture(async e=>{const previous=globalThis.ikunAuth;globalThis.ikunAuth=e.api;try{await fn(e);}finally{globalThis.ikunAuth=previous;}});}
function ports(overrides={}){
 const calls=[];return {calls,project:async()=>ok({project_id:pid,name:'测试项目',revision:7}),subscriptions:async()=>ok({items:[],next_cursor:null}),discoveries:async()=>ok({items:[],next_cursor:null}),create:async body=>{calls.push(body);return ok({subscription_id:sid,state:'accepted'});},...overrides};
}
const post=(e,body={},headers={})=>req(path,'POST',body,e.root,{'idempotency-key':randomUUID(),'if-match':'"rev-7"',...headers});
test('handle normalization and project/handle dedupe include stopped, exclude removed',()=>{
 for(const input of ['@ExaMple',' example '])assert.equal(normalizeXHandle(input),'example');
 for(const input of ['@@test','bad-name','https://x.com/a','a'.repeat(16),'',null,42])assert.equal(normalizeXHandle(input),null);
 assert.equal(existingTracking([entry({project_id:other,x_handle:'ExAmPlE',desired_state:'stopped'})],pid,'example')?.subscription_id,sid);
 assert.equal(existingTrackingMessage(entry({desired_state:'stopped'})),'已在追踪列表（已停止，可到追踪页恢复）');
 assert.equal(existingTracking([entry({desired_state:'removed'})],pid,'example'),undefined);
});
test('same project already tracked: no source request, command, resume or update',()=>run(async e=>{
 const p=ports({subscriptions:async()=>ok({items:[entry()],next_cursor:null}),discoveries:async()=>{throw Error('must not read');}});
 for(const request of [req(path,'GET',undefined,e.root),post(e)]){
  const response=await projectTrackingRoute(request,p);assert.equal(response.status,200);assert.equal((await response.json()).data.message,'已在追踪列表');
 }assert.deepEqual(p.calls,[]);
}));
test('cross-project same handle, stopped, second page: do not add or resume',()=>run(async e=>{
 const p=ports({subscriptions:async cursor=>ok({items:cursor?[entry({project_id:other,desired_state:'stopped',x_handle:'TeStAccount'})]:[],next_cursor:cursor?null:'second'}),discoveries:async()=>ok({items:[{project_id:pid,x_handle:'testaccount'}]})});
 const response=await projectTrackingRoute(post(e,{x_handle:'@TESTACCOUNT'}),p);
 assert.equal(response.status,200);assert.equal((await response.json()).data.message,'已在追踪列表（已停止，可到追踪页恢复）');assert.equal(p.calls.length,0);
}));
test('hunter-linked handle is used automatically; creation uses existing project and empty notes',()=>run(async e=>{
 const p=ports({discoveries:async state=>ok({items:state==='tracking'?[{project_id:pid,x_handle:'@TestAccount',x_user_id:'12345'}]:[]})});
 const ready=await projectTrackingRoute(req(path,'GET',undefined,e.root),p);assert.equal((await ready.json()).data.x_handle,'testaccount');
 const response=await projectTrackingRoute(post(e),p);assert.equal(response.status,200);assert.equal((await response.json()).data.message,'已加入追踪');
 assert.deepEqual(p.calls,[{project_id:pid,name:'测试项目',x_handle:'testaccount',x_user_id:'12345',notes:'',confirmed:true}]);
}));
test('ignored source is still available; unrelated hunter identities are not returned',()=>run(async e=>{
 const p=ports({discoveries:async state=>ok({items:state==='tracking'?[{project_id:other,x_handle:'privatehunter'}]:[{project_id:pid,x_handle:'target'}]})});
 const response=await projectTrackingRoute(req(path,'GET',undefined,e.root),p);const value=await response.json();assert.equal(value.data.x_handle,'target');assert.ok(!JSON.stringify(value).includes('privatehunter'));
}));
test('no source prompts manual entry; valid manual account can be created in mock only',()=>run(async e=>{
 const p=ports();const ready=await projectTrackingRoute(req(path,'GET',undefined,e.root),p);assert.equal((await ready.json()).data.x_handle,null);
 assert.equal((await projectTrackingRoute(post(e),p)).status,422);
 const response=await projectTrackingRoute(post(e,{x_handle:' @Manual_123 '}),p);assert.equal(response.status,200);assert.equal(p.calls[0].x_handle,'manual_123');assert.equal(p.calls[0].notes,'');
}));
test('malformed handle, extra body fields, bad key and stale revision reject before creation',()=>run(async e=>{
 const p=ports();
 for(const [body,headers,status] of [[{x_handle:'bad-name'},{},422],[{x_handle:'valid',notes:'injected'},{},422],[{x_handle:'valid'},{'idempotency-key':'bad'},422],[{x_handle:'valid'},{'if-match':'"rev-6"'},409]])assert.equal((await projectTrackingRoute(post(e,body,headers),p)).status,status);
 assert.equal(p.calls.length,0);
}));
test('changed hunter identity rejects stale manual confirmation',()=>run(async e=>{
 const p=ports({discoveries:async()=>ok({items:[{project_id:pid,x_handle:'new_handle'}]})});
 assert.equal((await projectTrackingRoute(post(e,{x_handle:'old_handle'}),p)).status,409);assert.equal(p.calls.length,0);
}));
test('unavailable or malformed subscription list fails closed, never assumed empty',()=>run(async e=>{
 for(const subscriptions of [async()=>Response.json({error:{message:'unavailable'}},{status:503}),async()=>ok({items:[{project_id:pid}]}),async()=>ok({items:[],next_cursor:'loop'})]){
  const p=ports({subscriptions});assert.equal((await projectTrackingRoute(post(e,{x_handle:'target'}),p)).status,503);assert.equal(p.calls.length,0);
 }
}));
test('source unavailable or ambiguous falls back to explicit manual entry',()=>run(async e=>{
 for(const discoveries of [async()=>{throw Error('unavailable');},async()=>ok({items:[{project_id:pid,x_handle:'first'},{project_id:pid,x_handle:'second'}]})]){
  const p=ports({discoveries});const value=await (await projectTrackingRoute(req(path,'GET',undefined,e.root),p)).json();assert.equal(value.data.x_handle,null);assert.ok(value.data.warning);assert.equal(p.calls.length,0);
 }
}));
test('concurrent conflict is reread and reported as already tracked, not retried',()=>run(async e=>{
 let reads=0;const p=ports({subscriptions:async()=>ok({items:++reads===1?[]:[entry({desired_state:'stopped'})]}),create:async()=>{p.calls.push('create');return Response.json({error:{message:'duplicate'}},{status:409});}});
 const response=await projectTrackingRoute(post(e,{x_handle:'example'}),p);assert.equal(response.status,200);assert.match((await response.json()).data.message,/已停止/);assert.equal(p.calls.length,1);
}));
test('creation failure and unknown result are not reported as success',()=>run(async e=>{
 for(const create of [async()=>Response.json({error:{message:'原始失败原因'}},{status:503}),async()=>ok({subscription_id:sid,state:'failed',error_code:'ownership_conflict'})]){
  const response=await projectTrackingRoute(post(e,{x_handle:'target'}),ports({create}));assert.ok(!response.ok);assert.ok(!(await response.text()).includes('已加入追踪'));
 }
}));
test('anonymous and reader cannot access or add; CSRF remains required for admin writes',()=>run(async e=>{
 const p=ports(),reader=await user(e);
 assert.equal((await projectTrackingRoute(req(path),p)).status,401);
 for(const method of ['GET','POST'])assert.equal((await projectTrackingRoute(req(path,method,method==='POST'?{x_handle:'target'}:undefined,reader.logged,{'idempotency-key':randomUUID(),'if-match':'"rev-7"'}),p)).status,403);
 const badCsrf=post(e,{x_handle:'target'});badCsrf.headers.set('x-csrf-token','wrong');assert.equal((await projectTrackingRoute(badCsrf,p)).status,403);assert.equal(p.calls.length,0);
}));
