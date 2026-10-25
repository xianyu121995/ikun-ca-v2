import {after,before,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import http from 'node:http';
import {Readable} from 'node:stream';
import {fileURLToPath} from 'node:url';
const preview=new URL('../../../../',import.meta.url);
const {ManagedProjectsIpc}=await import(new URL('packages/runtime/dist/index.js',preview));
const post=await import(new URL('apps/website/app/internal/v1/ingest/[source]/route.ts',preview));
const get=await import(new URL('apps/website/app/internal/v1/receipts/[source]/[id]/route.ts',preview));
const fixture=JSON.parse(readFileSync(process.env.TI_FIXTURE));
const entry=fileURLToPath(new URL('../ipc-entry.py',import.meta.url));
const options={executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:fileURLToPath(new URL('../../candidate/',import.meta.url)),entry_path:entry,
  entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:process.env.B2_BUILD_SHA};
let manager=new ManagedProjectsIpc(options,process.env.DATA_ROOT),origin,baseReceipt,lostReceipt,postCount=0;
const token='t'.repeat(64),hunter='h'.repeat(64),path='/internal/v1/ingest/tracking';
async function start(){await manager.start(15000);Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha,PROJECTS_INGEST_TRACKING_TOKEN:token,PROJECTS_INGEST_HUNTER_TOKEN:hunter});}
function request(url=path,{method='POST',raw=fixture.cases.base.raw,hash,bearer=token,headers={}}={}){
  return new Request((origin??'http://127.0.0.1:31996')+url,{method,headers:{'content-type':'application/json',...(bearer?{authorization:'Bearer '+bearer}:{}),...(hash?{'x-expected-event-sha256':hash}:{}),...headers},...(['GET','HEAD'].includes(method)?{}:{body:raw})});
}
const receiptPath=id=>'/internal/v1/receipts/tracking/'+id;
async function receipt(id,hash){return get.GET(request(receiptPath(id),{method:'GET',hash}));}
async function code(response,status,expected){assert.equal(response.status,status);const body=await response.json();assert.ok(body.request_id);assert.equal(response.headers.get('x-request-id'),body.request_id);assert.equal(response.headers.get('cache-control'),'no-store');if(expected)assert.equal(body.error.code,expected);if(status>=400)assert.equal('data' in body,false);return body;}
function modified(mutator){const event=structuredClone(fixture.event);event.event_id='evt_'+randomUUID();mutator(event);return JSON.stringify(event);}
const server=http.createServer(async(incoming,outgoing)=>{
  try{
    const headers=new Headers();for(const [key,value] of Object.entries(incoming.headers))if(value!==undefined)headers.set(key,Array.isArray(value)?value.join(','):value);
    const method=incoming.method;const native=new Request(origin+incoming.url,{method,headers,...(['GET','HEAD'].includes(method)?{}:{body:Readable.toWeb(incoming),duplex:'half'})});
    const response=method==='POST'?await post.POST(native):await get.GET(native);
    if(method==='POST'){
      postCount++;const body=await response.clone().json();
      if(body.data?.event_id===fixture.cases.lost_ack.event_id){lostReceipt=body.data;incoming.socket.destroy();return;}
    }
    outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(Buffer.from(await response.arrayBuffer()));
  }catch{outgoing.destroy();}
});
before(async()=>{await start();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;});
after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await manager.stop();});

test('Actual tracking route rejects cookies, forged roles and wrong direction credentials',async()=>{
  await code(await post.POST(request(path,{bearer:null,headers:{cookie:'synthetic=not-service','x-role':'superadmin','x-user-id':'fake'}})),401,'UNAUTHENTICATED');
  await code(await post.POST(request(path,{bearer:hunter})),401,'UNAUTHENTICATED');
  await code(await post.POST(request('/internal/v1/ingest/hunter')),401,'UNAUTHENTICATED');
});
test('Original Hunter route still creates its canonical command and stable receipt',async()=>{
  const event=fixture.hunter_event,options={raw:JSON.stringify(event),bearer:hunter};
  const first=(await code(await post.POST(request('/internal/v1/ingest/hunter',options)),200)).data;
  assert.equal(first.command_id,event.payload.command_id);assert.equal(first.duplicate,false);
  assert.deepEqual((await code(await post.POST(request('/internal/v1/ingest/hunter',options)),200)).data,{...first,duplicate:true});
  const found=await get.GET(request('/internal/v1/receipts/hunter/'+event.event_id,{method:'GET',bearer:hunter}));
  assert.deepEqual((await code(found,200)).data,{...first,duplicate:true});
});
test('Actual route -> UDS -> Python persists the exact event/hash and returns an original receipt',async()=>{
  const item=fixture.cases.base;const response=await post.POST(request(path,{raw:item.raw,hash:item.sha256}));baseReceipt=(await code(response,200)).data;
  assert.equal(baseReceipt.duplicate,false);assert.equal(baseReceipt.command_id,null);assert.equal(baseReceipt.project_id,fixture.project.project_id);
  const found=(await code(await receipt(item.event_id,item.sha256),200)).data;
  assert.deepEqual(found,{...baseReceipt,duplicate:true});
  assert.deepEqual((await code(await post.POST(request(path,{raw:item.raw,hash:item.sha256})),200)).data,found);
});
test('Real hash checks reject a changed event and a conflicting receipt lookup',async()=>{
  await code(await receipt(fixture.cases.base.event_id,'0'.repeat(64)),409,'CONFLICT');
  const event=JSON.parse(fixture.cases.base.raw);event.payload.text+=' changed';
  await code(await post.POST(request(path,{raw:JSON.stringify(event)})),409,'CONFLICT');
  await code(await post.POST(request(path,{hash:'not-a-hash'})),422,'VALIDATION_ERROR');
});
test('Updated visibility correction is accepted as metadata, never a new activity notification',async()=>{
  const item=fixture.cases.updated;await code(await post.POST(request(path,{raw:item.raw,hash:item.sha256})),200);
});
for(const name of ['max_emoji','max_control'])test('Maximum '+name+' and raw int64 survive actual route/RPC/hash without truncation',async()=>{
  const item=fixture.cases[name];assert.ok(Buffer.byteLength(item.raw)>65536&&Buffer.byteLength(item.raw)<131072);
  assert.ok(item.raw.includes('9223372036854775807'));
  await code(await post.POST(request(path,{raw:item.raw,hash:item.sha256})),200);
  await code(await receipt(item.event_id,item.sha256),200);
  await code(await post.POST(request(path,{raw:item.raw,hash:item.sha256})),200);
});
for(const name of ['fraction_schema','fraction_generation'])test('Raw numeric '+name+' is rejected rather than coerced to integer',async()=>{
  const item=fixture.cases[name];await code(await post.POST(request(path,{raw:item.raw,hash:item.sha256})),422,'VALIDATION_ERROR');
});
test('Tracking oversized body rejects 413 while Hunter remains at its original 64KiB bound',async()=>{
  const raw=fixture.cases.base.raw+' '.repeat(131073-Buffer.byteLength(fixture.cases.base.raw));
  await code(await post.POST(request(path,{raw})),413,'VALIDATION_ERROR');
  await code(await post.POST(request('/internal/v1/ingest/hunter',{raw:fixture.cases.max_emoji.raw,bearer:hunter})),422,'VALIDATION_ERROR');
});
test('Invalid UTF-8 and unpaired surrogate are rejected without replacement/hash repair',async()=>{
  const invalid=Buffer.concat([Buffer.from('{"x":"'),Buffer.from([0xed,0xa0,0x80]),Buffer.from('"}')]);
  await code(await post.POST(request(path,{raw:invalid})),422,'VALIDATION_ERROR');
  const bad=fixture.cases.base.raw.replace('仅校验hash，不持久化正文','\\ud800');
  assert.notEqual(bad,fixture.cases.base.raw);
  await code(await post.POST(request(path,{raw:bad})),422,'VALIDATION_ERROR');
});
test('Direction reuse, scope override, source mismatch and unrelated canonical fail closed',async()=>{
  const previous=process.env.TRACKING_API_TOKEN;process.env.TRACKING_API_TOKEN=token;
  try{await code(await post.POST(request()),503,'AUTH_NOT_CONFIGURED');}finally{if(previous===undefined)delete process.env.TRACKING_API_TOKEN;else process.env.TRACKING_API_TOKEN=previous;}
  await code(await post.POST(request(path,{headers:{'x-scope':'foreign'}})),403,'FORBIDDEN');
  await code(await post.POST(request(path,{raw:modified(event=>{event.source='hunter';})})),403,'FORBIDDEN');
  await code(await post.POST(request(path,{raw:modified(event=>{event.tenant_id='foreign';})})),403,'FORBIDDEN');
  await code(await post.POST(request(path,{raw:modified(event=>{event.project_id=event.payload.project_id='prj_'+randomUUID();})})),404,'NOT_FOUND');
  await code(await post.POST(request(path,{raw:modified(event=>{event.project_id=event.payload.project_id=fixture.other_project.project_id;})})),409,'CONFLICT');
});
test('A real loopback HTTP lost ACK is reconciled by GET with no blind second POST',async()=>{
  const item=fixture.cases.lost_ack,before=postCount;
  await assert.rejects(fetch(origin+path,{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'application/json','x-expected-event-sha256':item.sha256},body:item.raw}));
  assert.equal(postCount,before+1);assert.ok(lostReceipt);
  const response=await fetch(origin+receiptPath(item.event_id),{headers:{authorization:'Bearer '+token,'x-expected-event-sha256':item.sha256}});
  assert.deepEqual((await code(response,200)).data,{...lostReceipt,duplicate:true});assert.equal(postCount,before+1);
});
test('A real HTTP storage failure returns 503 and GET finds no manufactured receipt',async()=>{
  const item=fixture.cases.storage_fault;
  const failed=await fetch(origin+path,{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'application/json','x-expected-event-sha256':item.sha256},body:item.raw});
  const body=await code(failed,503,'DB_UNAVAILABLE');assert.equal(body.error.retryable,true);
  await code(await receipt(item.event_id,item.sha256),404,'NOT_FOUND');
});
test('Expired scrubbed bodies cannot POST; absent original receipt stays unknown with GET only',async()=>{
  const item=fixture.cases.unseen_expired,event=JSON.parse(item.raw);const scrub={};
  for(const key of ['schema_version','event_id','source','event_type','tenant_id','project_id','correlation_id','received_at'])scrub[key]=event[key];scrub.expired=true;
  await code(await post.POST(request(path,{raw:JSON.stringify(scrub)})),422,'VALIDATION_ERROR');
  const before=postCount;const response=await fetch(origin+receiptPath(item.event_id),{headers:{authorization:'Bearer '+token,'x-expected-event-sha256':item.sha256}});
  await code(response,404,'NOT_FOUND');assert.equal(postCount,before);
  await code(await receipt(fixture.cases.base.event_id,fixture.cases.base.sha256),200);
});
test('Receipt survives an actual managed IPC restart, without replaying its body',async()=>{
  await manager.stop();manager=new ManagedProjectsIpc(options,process.env.DATA_ROOT);await start();
  assert.deepEqual((await code(await receipt(fixture.cases.base.event_id,fixture.cases.base.sha256),200)).data,{...baseReceipt,duplicate:true});
});
