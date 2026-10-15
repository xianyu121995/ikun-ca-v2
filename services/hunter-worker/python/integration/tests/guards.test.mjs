import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {pathToFileURL,fileURLToPath} from 'node:url';
import path from 'node:path';
const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../var/b4/light');
const load=file=>import(pathToFileURL(path.join(base,file)));
const {AuthHttp}=await load('modules/auth/dist/src/http.js');
const {LocalAccounts}=await load('modules/auth/dist/src/local.js');
const {config}=await load('modules/auth/dist/src/config.js');
const route=await load('apps/website/app/api/v1/hunter/[...path]/route.js');
const {hunterEventsRoute}=await load('apps/website/lib/hunter.js');
const origin='http://127.0.0.1:3300',password='fixture-initial-passphrase',changed='fixture-changed-passphrase';
process.env.HUNTER_API_TOKEN='fixture-direction-'+('x'.repeat(32));process.env.IKUN_HUNTER_ORIGIN='http://127.0.0.1:3311';
function req(url,session,method='GET',body,extra={}){
 const headers={host:new URL(origin).host,...extra};if(session){headers.cookie='ikun_dev_session='+session.token;headers['x-csrf-token']=session.actor.csrf_token;}
 if(method!=='GET'){headers.origin=origin;headers['content-type']='application/json';}
 return new Request(origin+url,{method,headers,...(body===undefined?{}:{body:JSON.stringify(body)})});
}
async function fixture(run){
 const directory=mkdtempSync('/private/tmp/ikun-hunter-auth-fixture-');let now=1800000000;const store=new LocalAccounts(config({dataRoot:directory,origin,secure:false}),true,()=>now);
 const previousFetch=globalThis.fetch;const calls=[];
 try{
  await store.bootstrap('fixture_admin',password);const first=await store.login('fixture_admin',password);const admin=await store.changePassword(first.actor,password,changed);
  const user=await store.create('fixture_user',password),userFirst=await store.login('fixture_user',password);const reader=await store.changePassword(userFirst.actor,password,changed);
  globalThis.ikunAuth=new AuthHttp(store,[/^\/api\/v1\/hunter\/(?:signals|discoveries\/[^/]+)$/, /^\/api\/v1\/(?:events\/stream|commands\/cmd_[a-f0-9-]{36})$/],[/^\/hunter$/]);
  globalThis.fetch=async(url,options)=>{calls.push({url:String(url),...options});return Response.json({data:{items:[],next_cursor:null},request_id:options.headers['x-request-id']});};
  await run({store,admin,reader,user,calls,advance(seconds){now+=seconds;},setFetch(value){globalThis.fetch=value;}});
 }finally{globalThis.fetch=previousFetch;delete globalThis.ikunAuth;store.close();rmSync(directory,{recursive:true,force:true});}
}
test('actual Route Handler rejects anonymous and user writes without Proxy',()=>fixture(async e=>{
 assert.equal((await route.GET(req('/api/v1/hunter/signals'))).status,401);
 assert.equal((await route.POST(req('/api/v1/hunter/accounts',e.reader,'POST',{}))).status,403);
 assert.equal((await route.GET(req('/api/v1/hunter/accounts',e.reader))).status,403);
 assert.equal(e.calls.length,0);
 assert.equal((await route.GET(req('/api/v1/hunter/signals',e.reader))).status,200);
}));
test('trusted principal replaces forged browser headers, no cookie forwarded',()=>fixture(async e=>{
 const result=await route.POST(req('/api/v1/hunter/accounts',e.admin,'POST',{x_handle:'fixture'},{'x-role':'user','x-ikun-principal':'forged','authorization':'Bearer browser','x-request-id':'safe-id'}));
 assert.equal(result.status,200);assert.equal(result.headers.get('cache-control'),'no-store, private');
 const headers=e.calls[0].headers;assert.equal(JSON.parse(headers['x-ikun-principal']).user_id,e.admin.actor.id);assert.equal(headers.cookie,undefined);assert.equal(headers.authorization,'Bearer '+process.env.HUNTER_API_TOKEN);
}));
test('foreign Request implementation is reconstructed from explicit fields',()=>fixture(async e=>{
 const request=req('/api/v1/hunter/signals',e.reader);
 const foreign={url:request.url,headers:request.headers,method:request.method,body:null,signal:request.signal};
 assert.equal((await route.GET(foreign)).status,200);assert.equal(e.calls.length,1);
}));
test('research PATCH preserves raw JSON and forwards only concurrency headers',()=>fixture(async e=>{
 const source=req('/api/v1/hunter/discoveries/dsc_2ef30fbb-13de-4a22-95f3-84d67e1af814',e.admin,'PATCH',{}, {'if-match':'"rev-4"','idempotency-key':'087cd0aa-0f13-4adc-b632-55dc5d35dfc2','x-role':'forged'});
 const raw='{"notes":"one","notes":"two"}',request=new Request(source.url,{method:'PATCH',headers:source.headers,body:raw});
 assert.equal((await route.PATCH(request)).status,200);
 assert.equal(e.calls[0].body,raw,'worker must receive duplicate keys to reject them, not silently flatten JSON');
 assert.equal(e.calls[0].headers['if-match'],'"rev-4"');assert.equal(e.calls[0].headers['idempotency-key'],'087cd0aa-0f13-4adc-b632-55dc5d35dfc2');assert.equal(e.calls[0].headers['x-role'],undefined);
}));
test('CSRF, Origin and Host are checked in the actual handler',()=>fixture(async e=>{
 for(const [header,value] of [['origin','http://bad.example'],['host','bad.example'],['x-csrf-token','wrong']]){
  const request=req('/api/v1/hunter/accounts',e.admin,'POST',{});request.headers.set(header,value);assert.notEqual((await route.POST(request)).status,200);
 }
 assert.equal(e.calls.length,0);
}));
test('force-change, disable, enable and reset revoke actual sessions',()=>fixture(async e=>{
 const temporary=await e.store.create('fresh_user',password),login=await e.store.login('fresh_user',password);
 assert.equal((await route.GET(req('/api/v1/hunter/signals',login))).status,403);
 e.store.setEnabled('fixture_user',false);assert.equal((await route.GET(req('/api/v1/hunter/signals',e.reader))).status,401);
 e.store.setEnabled('fixture_user',true);assert.equal((await route.GET(req('/api/v1/hunter/signals',e.reader))).status,401);
 await e.store.reset('fixture_admin',password);assert.equal((await route.GET(req('/api/v1/hunter/signals',e.admin))).status,401);
}));
test('password rotation and absolute seven day expiry are enforced',()=>fixture(async e=>{
 const rotated=await e.store.changePassword(e.reader.actor,changed,password);
 assert.equal((await route.GET(req('/api/v1/hunter/signals',e.reader))).status,401);
 assert.equal((await route.GET(req('/api/v1/hunter/signals',rotated))).status,200);
 e.advance(604801);assert.equal((await route.GET(req('/api/v1/hunter/signals',e.admin))).status,401);
}));
test('SSE frames are enveloped and resume the original stable event sequence',()=>fixture(async e=>{
 e.setFetch(async(url,options)=>{e.calls.push(String(url));return Response.json({data:{items:[{sequence:8,type:'hunter.discovery.updated',data:{discovery_id:'fixture',signal_count:2}}]},request_id:options.headers['x-request-id']});});
 const response=await hunterEventsRoute(req('/api/v1/events/stream',e.reader,'GET',undefined,{'last-event-id':'hunter:7','x-request-id':'sse-fixture'}));const reader=response.body.getReader();const chunk=new TextDecoder().decode((await reader.read()).value);
 assert.match(e.calls[0],/after=7$/);assert.match(chunk,/id: hunter:8/);const frame=JSON.parse(chunk.split('data: ')[1].trim());assert.equal(frame.request_id,'sse-fixture');assert.equal(frame.data.signal_count,2);await reader.cancel();
}));
test('silent SSE revocation cancels the upstream polling work',()=>fixture(async e=>{
 const response=await hunterEventsRoute(req('/api/v1/events/stream',e.reader));const reader=response.body.getReader();const pending=reader.read();
 e.store.setEnabled('fixture_user',false);const result=await Promise.race([pending,new Promise((_,reject)=>setTimeout(()=>reject(Error('revocation deadline')),2500))]);assert.equal(result.done,true);
 const count=e.calls.length;await new Promise(resolve=>setTimeout(resolve,650));assert.equal(e.calls.length,count);
}));
test('upstream failure stays explicit and never falls back to demo',()=>fixture(async e=>{
 e.setFetch(async()=>{throw Error('fixture-offline');});const result=await route.GET(req('/api/v1/hunter/signals',e.reader));assert.equal(result.status,502);assert.equal((await result.json()).error.code,'UPSTREAM_UNAVAILABLE');
}));
