import {after,before,test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {chmodSync,mkdtempSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
const {ipc}=await import(new URL('../../.preview/apps/website/lib/projects.ts',import.meta.url));
const directory=mkdtempSync('/private/tmp/ikp-rating-');chmodSync(directory,0o700);const socketPath=join(directory,'p.sock');
const names=['IKUN_PROJECTS_IPC_SOCKET','IKUN_PROJECTS_IPC_TOKEN','IKUN_PROJECTS_BUILD_SHA'];const old=names.map(name=>process.env[name]);
const token='r'.repeat(64),build='f'.repeat(40);let mode='valid',closed,entered;let received=0;
const server=http.createServer((request,response)=>{
  received++;
  closed=new Promise(resolve=>response.once('close',resolve));
  assert.equal(request.headers.authorization,'Bearer '+token);assert.equal(request.headers['x-ikun-build-sha'],build);
  let body='';request.on('data',part=>{body+=part;});request.on('end',()=>{
    const value=JSON.parse(body);assert.equal(value.operation,'ratings');assert.equal(value.contract,'tracking-ratings-v1');assert.equal(value.principal.role,'user');
    entered?.();entered=undefined;
    if(mode==='stall')return;
    if(mode==='bad_json'){response.end('{');return;}
    const request_id=mode==='wrong_request_id'?'wrong':value.request_id;
    response.setHeader('content-type','application/json');
    if(typeof mode==='number'){response.statusCode=mode;response.end(JSON.stringify({error:{code:mode===409?'VERSION_CONFLICT':'VALIDATION_ERROR',message:'synthetic',retryable:false},request_id}));return;}
    const data={contract:'tracking-ratings-v1',catalog_version:'fixture',checked_at:new Date().toISOString(),items:value.body.project_ids.map(project_id=>({project_id,state:'missing',rating:null,revision:null}))};
    if(mode==='wrong_contract')data.contract='wrong';
    if(mode==='missing_item')data.items=[];
    if(mode==='duplicate_item')data.items.push(data.items[0]);
    if(mode==='invalid_found')data.items[0].state='found';
    if(mode==='invalid_missing')data.items[0].rating='A';
    response.end(JSON.stringify({data,request_id}));
  });
});
before(async()=>{
  Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:socketPath,IKUN_PROJECTS_IPC_TOKEN:token,IKUN_PROJECTS_BUILD_SHA:build});
  await new Promise(resolve=>server.listen(socketPath,resolve));chmodSync(socketPath,0o600);
});
after(async()=>{
  server.closeAllConnections();await new Promise(resolve=>server.close(resolve));rmSync(directory,{recursive:true,force:true});
  names.forEach((name,index)=>{if(old[index]===undefined)delete process.env[name];else process.env[name]=old[index];});
});
const query=(ids=[])=>({operation:'ratings',contract:'tracking-ratings-v1',principal:{user_id:'fixture_user',tenant_id:'ikun-main',role:'user'},request_id:randomUUID(),body:{project_ids:ids,expected_catalog_version:null}});
async function unavailable(response){assert.equal(response.status,503);const value=await response.json();assert.equal(value.error.code,'UPSTREAM_UNAVAILABLE');assert.equal('data' in value,false);assert.equal(value.request_id,response.headers.get('x-request-id'));}
async function upstreamClosed(){let timer;try{await Promise.race([closed,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('UPSTREAM_NOT_CANCELLED')),500);})]);}finally{clearTimeout(timer);}}

test('Ratings uses existing UDS credentials and exact request ID envelope',async()=>{
  mode='valid';const payload=query(),response=await ipc(payload);assert.equal(response.status,200);assert.equal((await response.json()).request_id,payload.request_id);
});
for(const status of [409,422])test('Ratings preserves domain '+status,async()=>{
  mode=status;const response=await ipc(query());assert.equal(response.status,status);assert.equal('data' in await response.json(),false);
});
for(const value of ['bad_json','wrong_request_id'])test('Ratings rejects '+value+' as unavailable, never missing',async()=>{
  mode=value;await unavailable(await ipc(query()));
});
for(const value of ['wrong_contract','missing_item','duplicate_item','invalid_found','invalid_missing'])test('Ratings rejects invalid projection '+value,async()=>{
  mode=value;await unavailable(await ipc(query(['prj_550e8400-e29b-41d4-a716-446655440000'])));
});
test('Ratings normalizes source 503 without partial success',async()=>{mode=503;await unavailable(await ipc(query()));});
test('Missing IPC configuration is unavailable, never an empty catalog',async()=>{
  delete process.env.IKUN_PROJECTS_IPC_SOCKET;
  try{await unavailable(await ipc(query()));}finally{process.env.IKUN_PROJECTS_IPC_SOCKET=socketPath;}
});
test('Ratings deadline is two seconds and cancels the real upstream socket',async()=>{
  mode='stall';const before=received,start=Date.now();await unavailable(await ipc(query()));assert.ok(Date.now()-start>=1800&&Date.now()-start<2800);assert.equal(received,before+1);await upstreamClosed();
});
test('Caller cancellation reaches the upstream, without retry',async()=>{
  mode='stall';const abort=new AbortController(),before=received;const accepted=new Promise(resolve=>{entered=resolve;});let timer;
  const pending=ipc(query(),abort.signal);
  try{
    await Promise.race([accepted,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('UPSTREAM_NOT_ENTERED')),500);})]);
    const start=Date.now();abort.abort();await unavailable(await pending);assert.ok(Date.now()-start<1000);assert.equal(received,before+1);await upstreamClosed();
  }finally{clearTimeout(timer);entered=undefined;abort.abort();}
});
