import {AsyncLocalStorage} from 'node:async_hooks';
import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import http,{createServer} from 'node:http';
import {dirname} from 'node:path';
globalThis.AsyncLocalStorage=AsyncLocalStorage;
const preview=new URL('../../.preview/',import.meta.url);
const {ManagedProjectsIpc}=await import(new URL('packages/runtime/dist/index.js',preview));
const {LocalAccounts}=await import(new URL('modules/auth/dist/src/local.js',preview));
const {environment}=await import(new URL('modules/auth/dist/src/config.js',preview));
const credentials=JSON.parse(readFileSync(process.env.TEST_ACCOUNTS));
const entry=fileURLToPath(new URL('../ipc-entry.py',import.meta.url));
const manager=new ManagedProjectsIpc({executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:fileURLToPath(new URL('../../candidate/',import.meta.url)),entry_path:entry,
  entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:process.env.B2_BUILD_SHA},process.env.DATA_ROOT);
let projects,events,auth,store,route,action,pageGuard,work,unit;
const fields={name:'Direct entry',rating:'A',description:'',website_url:null,notes:'',category:null,progress_stage:'researching',progress_percent:null,token_date:null,token_date_status:'unconfirmed'};
function req(path,method='GET',session,body){return new Request(process.env.IKUN_AUTH_ORIGIN+path,{method,headers:{host:new URL(process.env.IKUN_AUTH_ORIGIN).host,origin:process.env.IKUN_AUTH_ORIGIN,'content-type':'application/json',...(session?{cookie:session.cookie,'x-csrf-token':session.csrf}:{}),'idempotency-key':randomUUID()},...(body!==undefined?{body:JSON.stringify(body)}:{})});}
async function session(role){const response=await auth.handle(req('/api/v1/auth/login','POST',undefined,credentials[role]));assert.equal(response.status,200);const value=await response.json();return {cookie:response.headers.get('set-cookie').split(';')[0],csrf:value.data.csrf_token};}
async function quietRequest(session){const request=req('/api/v1/events/stream','GET',session);const principal=auth.principal(request);const response=await projects.ipc({operation:'changes',principal,request_id:randomUUID(),query:{after:'0'}});const items=(await response.json()).data.items;request.headers.set('last-event-id',String(items.at(-1)?.sequence??0));return request;}
async function context(request,fn){return work.run({route:'/',isStaticGeneration:false},()=>unit.run({type:'request',phase:'action',headers:request.headers},fn));}
before(async()=>{
  await manager.start(15000);Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha});
  projects=await import(new URL('apps/website/lib/projects.ts',preview));events=await import(new URL('apps/website/lib/project-events.ts',preview));auth=projects.projectsAuth();store=new LocalAccounts(environment());
  route=await import(new URL('apps/website/app/api/v1/projects/[[...path]]/route.ts',preview));
  ({createProjectAction:action}=await import(new URL('apps/website/app/project-actions.ts',preview)));
  ({requireAuthPage:pageGuard}=await import(new URL('apps/website/lib/auth.ts',preview)));
  ({workAsyncStorage:work}=await import(new URL('apps/website/node_modules/next/dist/server/app-render/work-async-storage.external.js',preview)));
  ({workUnitAsyncStorage:unit}=await import(new URL('apps/website/node_modules/next/dist/server/app-render/work-unit-async-storage.external.js',preview)));
});
after(async()=>{store?.close();auth?.store.close();await manager.stop();});

test('Actual route GET/POST bypassing Proxy validates cookie, scope, role and CSRF',async()=>{
  assert.equal((await route.GET(req('/api/v1/projects'))).status,401);
  const user=await session('user'),admin=await session('admin');
  assert.equal((await route.GET(req('/api/v1/projects/home-summary','GET',user))).status,200);
  assert.equal((await route.POST(req('/api/v1/projects','POST',user,fields))).status,403);
  const forged=req('/api/v1/projects','POST',undefined,fields);forged.headers.set('x-role','superadmin');forged.headers.set('x-user-id','fake');assert.equal((await route.POST(forged)).status,401);
  const csrf=req('/api/v1/projects','POST',admin,fields);csrf.headers.delete('x-csrf-token');assert.equal((await route.POST(csrf)).status,403);
  const origin=req('/api/v1/projects','POST',admin,fields);origin.headers.set('origin','http://evil.invalid');assert.equal((await route.POST(origin)).status,403);
  const host=req('/api/v1/projects','POST',admin,fields);host.headers.set('host','evil.invalid');assert.equal((await route.POST(host)).status,400);
  assert.equal((await route.GET(req('/api/v1/projects?tenant_id=foreign','GET',admin))).status,403);
  assert.equal((await route.POST(req('/api/v1/projects','POST',admin,fields))).status,201);
  const forced=await session('forced');assert.equal((await route.GET(req('/api/v1/projects','GET',forced))).status,403);
});
test('Actual page guard and Server Action bypassing Proxy validate B1 identity',async()=>{
  await assert.rejects(context(req('/'),()=>pageGuard('/')));
  const user=await session('user'),admin=await session('admin');
  assert.equal((await context(req('/','GET',user),()=>pageGuard('/'))).role,'user');
  await assert.rejects(context(req('/','POST',user),()=>action(user.csrf,randomUUID(),fields)));
  await assert.rejects(context(req('/','POST',admin),()=>action('wrong',randomUUID(),fields)));
  const result=await context(req('/','POST',admin),()=>action(admin.csrf,randomUUID(),{...fields,name:'Action entry'}));assert.equal(result.status,201);
});
test('Actual Next SSE data envelope, safe DTO, Last-Event-ID replay and upstream cancellation',async()=>{
  const {GET}=await import(new URL('apps/website/app/api/v1/events/stream/route.ts',preview));
  const admin=await session('admin'),user=await session('user');
  const request=await quietRequest(user);request.headers.set('x-request-id','B2_REV_001_first');
  async function create(name){const response=await route.POST(req('/api/v1/projects','POST',admin,{...fields,name}));assert.equal(response.status,201);return (await response.json()).data;}
  async function frame(reader){
    const decoder=new TextDecoder();let buffer='';const deadline=Date.now()+3000;
    while(Date.now()<deadline){
      let timer;const part=await Promise.race([reader.read(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('SSE_DATA_TIMEOUT')),Math.max(1,deadline-Date.now()));})]).finally(()=>clearTimeout(timer));
      assert.equal(part.done,false);buffer+=decoder.decode(part.value,{stream:true});
      let end;while((end=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2);if(!block.includes('data: '))continue;
        const fields=Object.fromEntries(block.split('\n').map(line=>{const at=line.indexOf(': ');return [line.slice(0,at),line.slice(at+2)];}));
        return {id:fields.id,event:fields.event,envelope:JSON.parse(fields.data)};
      }
    }
    throw Error('SSE_DATA_TIMEOUT');
  }
  function check(value,response,expected){
    assert.match(value.id,/^\d+$/);assert.equal(value.event,'project.updated');
    assert.deepEqual(Object.keys(value.envelope).sort(),['data','request_id']);
    assert.match(value.envelope.request_id,/^[A-Za-z0-9_-]{1,64}$/);assert.equal(value.envelope.request_id,response.headers.get('x-request-id'));
    assert.deepEqual(value.envelope.data,expected);
    assert.deepEqual(Object.keys(value.envelope.data).sort(),['project_id','name','rating','description','website_url','notes','category','progress_stage','progress_percent','token_date','token_date_status','home_membership','discovered_at','revision','created_at','updated_at'].sort());
  }
  const original=http.request;let calls=0;const readers=[];
  http.request=function(...args){if(args[0]?.socketPath===manager.identity.socketPath)calls++;return Reflect.apply(original,this,args);};
  try{
    const first=await create('SSE envelope first'),response=await GET(request);assert.equal(response.status,200);
    const reader=response.body.getReader();readers.push(reader);const one=await frame(reader);check(one,response,first);assert.equal(one.envelope.request_id,'B2_REV_001_first');
    await reader.cancel();const stopped=calls;await new Promise(resolve=>setTimeout(resolve,650));assert.equal(calls,stopped,'cancelled stream must stop upstream IPC polling');
    const second=await create('SSE envelope replay');const replay=req('/api/v1/events/stream','GET',user);replay.headers.set('last-event-id',one.id);
    const resumed=await GET(replay);assert.equal(resumed.status,200);const replayReader=resumed.body.getReader();readers.push(replayReader);
    const two=await frame(replayReader);check(two,resumed,second);assert.ok(Number(two.id)>Number(one.id));assert.notEqual(two.envelope.data.project_id,one.envelope.data.project_id);
    await replayReader.cancel();const replayStopped=calls;await new Promise(resolve=>setTimeout(resolve,650));assert.equal(calls,replayStopped);
  }finally{await Promise.all(readers.map(reader=>reader.cancel().catch(()=>{})));http.request=original;}
});
test('Actual SSE closes a quiet stream after logout and rejects the revoked API cookie',async()=>{
  const user=await session('user');
  const response=await events.projectEvents(req('/api/v1/events/stream','GET',user));assert.equal(response.status,200);
  const reader=response.body.getReader();await reader.read();
  assert.equal((await auth.handle(req('/api/v1/auth/logout','POST',user,{}))).status,200);
  let ended=false;for(let i=0;i<10;i++){const item=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('SSE_NOT_CLOSED')),3000))]);if(item.done){ended=true;break;}}
  assert.ok(ended);assert.equal((await route.GET(req('/api/v1/projects','GET',user))).status,401);
});
test('Actual SSE suppresses queued data when B1 account is disabled',async()=>{
  const user=await session('user');const response=await events.projectEvents(req('/api/v1/events/stream','GET',user));const reader=response.body.getReader();await reader.read();
  store.setEnabled('testuser',false);
  const admin=await session('admin');await route.POST(req('/api/v1/projects','POST',admin,{...fields,name:'Revoked data'}));
  const next=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('REVOCATION_TIMEOUT')),3000))]);assert.equal(next.done,true);
  assert.equal((await route.GET(req('/api/v1/projects','GET',user))).status,401);store.setEnabled('testuser',true);
});
test('Seven-day absolute expiry is enforced at the actual Projects handler',async()=>{
  const user=await session('user');const stream=await events.projectEvents(await quietRequest(user));const reader=stream.body.getReader();await reader.read();
  store.db.prepare('UPDATE auth_sessions SET created_at=created_at-604801 WHERE user_id=(SELECT id FROM auth_users WHERE username=?)').run('testuser');
  assert.equal((await route.GET(req('/api/v1/projects','GET',user))).status,401);
  const item=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('EXPIRED_STREAM_OPEN')),3000))]);assert.equal(item.done,true);
});
test('Local B1 password reset revokes active API and quiet SSE and forces password change',async()=>{
  const user=await session('user');const stream=await events.projectEvents(await quietRequest(user));const reader=stream.body.getReader();await reader.read();
  const reset='Synthetic-Reset-B2-482!';await store.reset('testuser',reset);
  assert.equal((await route.GET(req('/api/v1/projects','GET',user))).status,401);
  const item=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('RESET_STREAM_OPEN')),3000))]);assert.equal(item.done,true);
  const login=await store.login('testuser',reset);assert.equal(login.actor.must_change_password,true);
  await store.changePassword(login.actor,reset,credentials.user.password);
});
test('Password change rotates cookie atomically and revokes both previous sessions and quiet SSE',async()=>{
  const user=await session('user'),second=await session('user');
  const stream=await events.projectEvents(await quietRequest(user));const reader=stream.body.getReader();await reader.read();
  const changed=await auth.handle(req('/api/v1/auth/password','POST',user,{current_password:credentials.user.password,new_password:'Synthetic-Rotated-B2-849!'}));assert.equal(changed.status,200);
  const nextCookie=changed.headers.get('set-cookie').split(';')[0];assert.notEqual(nextCookie,user.cookie);
  assert.equal((await route.GET(req('/api/v1/projects','GET',user))).status,401);assert.equal((await route.GET(req('/api/v1/projects','GET',second))).status,401);
  assert.equal((await route.GET(req('/api/v1/projects','GET',{cookie:nextCookie,csrf:''}))).status,200);
  const item=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('PASSWORD_STREAM_NOT_REVOKED')),3000))]);assert.equal(item.done,true);
});
test('Lost Tracking ACK is reconciled by original command ID with no blind second POST',async()=>{
  const {relayOnce}=await import(new URL('apps/website/lib/outbox-relay.ts',preview));const actor={user_id:'fixture_admin',tenant_id:'ikun-main',role:'superadmin'};
  const command_id='cmd_'+randomUUID();const envelope={schema_version:1,event_id:'evt_'+randomUUID(),source:'hunter',event_type:'hunter.monitoring_requested',occurred_at:null,received_at:new Date().toISOString(),tenant_id:'ikun-main',project_id:null,correlation_id:randomUUID(),
    payload:{command_id,discovery_id:'fixture-lost-ack',source_entity_key:'fixture-lost-ack',confirmed:true,actor,project:{...fields,name:'Lost ACK'},x_user_id:'99887',x_handle:'fixture_user'}};
  const accepted=await projects.ipc({operation:'ingest',source:'hunter',request_id:randomUUID(),body:envelope});assert.equal(accepted.status,200);const project_id=(await accepted.json()).data.project_id;
  let posts=0,gets=0;
  const remote=createServer((request,response)=>{
    assert.equal(request.headers.authorization,'Bearer '+('t'.repeat(64)));
    if(request.method==='POST'){posts++;request.resume();request.on('end',()=>response.destroy());return;}
    gets++;assert.equal(request.url,'/internal/v1/commands/'+command_id);
    response.setHeader('content-type','application/json');response.end(JSON.stringify({data:{command_id,state:'succeeded',project_id,subscription_id:'sub_'+randomUUID(),revision:1,updated_at:new Date().toISOString(),error_code:null,request_id:randomUUID()},request_id:randomUUID()}));
  });
  await new Promise(resolve=>remote.listen(0,'127.0.0.1',resolve));
  try{const config={origin:'http://127.0.0.1:'+remote.address().port,token:'t'.repeat(64)};await relayOnce(config,command_id);await relayOnce(config,command_id);
    assert.equal(posts,1);assert.equal(gets,1);const result=await projects.ipc({operation:'command',principal:actor,target:command_id,request_id:randomUUID()});assert.equal((await result.json()).data.state,'succeeded');
  }finally{await new Promise(resolve=>remote.close(resolve));}
});
test('B0 rejects entry drift and bounds a failed real child startup',async()=>{
  const config={executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:fileURLToPath(new URL('../../candidate/',import.meta.url)),entry_path:entry,entry_sha256:'0'.repeat(64),build_sha:process.env.B2_BUILD_SHA};
  assert.throws(()=>new ManagedProjectsIpc(config,process.env.DATA_ROOT),/PROJECTS_ENTRY_MISMATCH/);
  const bad=new ManagedProjectsIpc({...config,args:[entry,'--invalid-startup-fixture'],entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex')},process.env.DATA_ROOT);
  const start=Date.now();await assert.rejects(bad.start(500),/PROJECTS_IPC_NOT_READY/);assert.ok(Date.now()-start<3000);assert.equal(existsSync(dirname(bad.identity.socketPath)),false);
});
