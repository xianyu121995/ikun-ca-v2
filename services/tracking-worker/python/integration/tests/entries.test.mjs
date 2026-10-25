import {AsyncLocalStorage} from 'node:async_hooks';
import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,mkdtempSync,writeFileSync,realpathSync,mkdirSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {join} from 'node:path';
import {createServer} from 'node:http';

globalThis.AsyncLocalStorage=AsyncLocalStorage;
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url)),preview=process.env.IKUN_TEST_REPO_ROOT||join(moduleRoot,'../../..');
const dataRoot=realpathSync(mkdtempSync('/private/tmp/ik-b3-entry-'));
const python=process.env.IKUN_TEST_PYTHON||join(moduleRoot,'.venv/bin/python'),token='b3-tracking-direction-credential-xxxxxxxx',fixtureToken=randomUUID();
const password='Synthetic-B3-Password-Final-274!',initial='Synthetic-B3-Initial-984!';
const {config}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/config.js')));
const {LocalAccounts}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/local.js')));
const {ManagedProjectsIpc,spawnManaged}=await import(pathToFileURL(join(preview,'packages/runtime/dist/index.js')));
let manager,managed,api,projects,auth,local,route,eventsRoute,pageGuard,action,work,unit,endpoint;
const fields={name:'B3 canonical',rating:'A',description:'',website_url:null,notes:'actual project note',category:null,progress_stage:'watching',progress_percent:null,token_date:null,token_date_status:'unconfirmed'};
const origin='http://127.0.0.1:3490';
function req(path,method='GET',session,body,headers={}){return new Request(origin+path,{method,headers:{host:new URL(origin).host,origin,'content-type':'application/json','idempotency-key':randomUUID(),...(session?{cookie:session.cookie,'x-csrf-token':session.csrf}:{}),...headers},...(body!==undefined?{body:JSON.stringify(body)}:{})});}
async function session(name){const response=await auth.handle(req('/api/v1/auth/login','POST',null,{username:name,password:name==='forced'?initial:password}));assert.equal(response.status,200);return {cookie:response.headers.get('set-cookie').split(';')[0],csrf:(await response.json()).data.csrf_token};}
async function createProject(admin,name='B3 canonical',patch={}){const response=await projects.projectsRoute(req('/api/v1/projects','POST',admin,{...fields,name,...patch}));assert.equal(response.status,201,JSON.stringify(await response.clone().json()));return (await response.json()).data;}
async function createSub(admin,project,handle='project1'){return route.POST(req('/api/v1/tracking/subscriptions','POST',admin,{project_id:project.project_id,name:project.name,x_handle:handle,x_user_id:null,notes:'subscription note first',confirmed:true}));}
async function until(fn){for(let i=0;i<120;i++){try{const value=await fn();if(value)return value;}catch{}await new Promise(r=>setTimeout(r,50));}throw Error('LOCAL_CONDITION_TIMEOUT');}
async function internal(path,options={}){return fetch(endpoint+'/internal/v1/'+path,{...options,headers:{authorization:'Bearer '+token,'content-type':'application/json',...options.headers}});}
async function state(sid){return (await(await internal('subscriptions/'+sid)).json()).data;}
async function fixture(path,body){return fetch(endpoint+'/fixture/'+path,{method:body?'POST':'GET',headers:{'x-fixture-token':fixtureToken,'content-type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});}
async function context(request,fn){return work.run({route:'/',isStaticGeneration:false},()=>unit.run({type:'request',phase:'action',headers:request.headers},fn));}
async function eventBlock(reader){let text='';for(let i=0;i<30;i++){const part=await reader.read();if(part.done)throw Error('SSE_ENDED_BEFORE_EVENT');text+=new TextDecoder().decode(part.value);if(/data: (.+)/.test(text))return text;}throw Error('SSE_EVENT_NOT_FOUND');}
before(async()=>{
 process.env.DATA_ROOT=dataRoot;process.env.IKUN_AUTH_ORIGIN=origin;process.env.IKUN_AUTH_DEV='1';
 // This rotation case needs two concurrent fixture sessions; the production default is one.
 process.env.IKUN_AUTH_MAX_SESSIONS='5';
 local=new LocalAccounts(config({dataRoot,origin,secure:false}),true);
 await local.bootstrap('admin',initial);await local.create('user',initial);await local.create('forced',initial);
 for(const name of ['admin','user']){const login=await local.login(name,initial);await local.changePassword(login.actor,initial,password);}
 const projectsEntry=join(preview,'modules/projects/integration/ipc-entry.py');
 execFileSync(python,[projectsEntry,'--migrate','--database',join(dataRoot,'projects/projects.db')]);
 manager=new ManagedProjectsIpc({executable:python,args:[projectsEntry],cwd:join(preview,'modules/projects/candidate'),entry_path:projectsEntry,entry_sha256:createHash('sha256').update(readFileSync(projectsEntry)).digest('hex'),build_sha:process.env.IKUN_TEST_BUILD_SHA||execFileSync('git',['rev-parse','HEAD'],{cwd:preview,encoding:'utf8'}).trim()},dataRoot);
 await manager.start(15000);Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha});
 const reserve=createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));endpoint='http://127.0.0.1:'+port;
 const cfg=join(dataRoot,'tracking.json');writeFileSync(cfg,JSON.stringify({db_path:join(dataRoot,'tracking/tracking.db'),remote_enabled:true,dedicated_account:true,port,reconcile_seconds:.1,backfill_seconds:.2,request_interval:0,heartbeat_seconds:.1,heartbeat_timeout:.5}));
 execFileSync(python,['-m','tracking.cli','init','--config',cfg],{cwd:moduleRoot});
 managed=spawnManaged(python,[join(moduleRoot,'integration/tests/fixture-tracking.py'),cfg,fixtureToken],{cwd:moduleRoot,env:{PATH:process.env.PATH,TRACKING_API_TOKEN:token,IKUN_TRACKING_6551_TOKEN:'fixture-provider-token-not-a-real-secret'},inheritOutput:true,graceMs:3000});
 await until(async()=>{const r=await fetch(endpoint+'/health/ready');return r.ok;});
 process.env.TRACKING_API_URL=endpoint;process.env.TRACKING_API_TOKEN=token;
 projects=await import(pathToFileURL(join(preview,'apps/website/lib/projects.ts')));projects.projectsAuth();
 api=await import(pathToFileURL(join(preview,'apps/website/lib/tracking.ts')));
 route=await import(pathToFileURL(join(preview,'apps/website/app/api/v1/tracking/[[...path]]/route.ts')));
 eventsRoute=await import(pathToFileURL(join(preview,'apps/website/app/api/v1/tracking/events/route.ts')));
 const authModule=await import(pathToFileURL(join(preview,'modules/auth/dist/src/server.js')));auth=authModule.auth();
 ({requireAuthPage:pageGuard}=await import(pathToFileURL(join(preview,'apps/website/lib/auth.ts'))));
 ({authorizeTrackingAction:action}=await import(pathToFileURL(join(preview,'apps/website/app/tracking/actions.ts'))));
 ({workAsyncStorage:work}=await import(pathToFileURL(join(preview,'apps/website/node_modules/next/dist/server/app-render/work-async-storage.external.js'))));
 ({workUnitAsyncStorage:unit}=await import(pathToFileURL(join(preview,'apps/website/node_modules/next/dist/server/app-render/work-unit-async-storage.external.js'))));
});
after(async()=>{auth?.store.close();local?.close();await managed?.stop();await manager?.stop();});

test('B1 actual Route Handler, page and Server Action deny anonymous/user/forced and forged identity',async()=>{
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions'))).status,401);
 const admin=await session('admin'),user=await session('user'),forced=await session('forced');
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,200);
 const authSingleton=(await import(pathToFileURL(join(preview,'modules/auth/dist/src/server.js')))).auth();await route.GET(req('/api/v1/tracking/subscriptions','GET',user));assert.equal((await import(pathToFileURL(join(preview,'modules/auth/dist/src/server.js')))).auth(),authSingleton);
 const configured=process.env.TRACKING_API_URL;process.env.TRACKING_API_URL='invalid configured origin';try{assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,503);}finally{process.env.TRACKING_API_URL=configured;}
 const project=await createProject(admin);
 assert.equal((await createSub(user,project)).status,403);
 assert.equal((await auth.handle(req('/api/auth/session','GET',forced))).status,200);
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',forced))).status,403);
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',null,undefined,{'x-role':'superadmin','x-user-id':'admin'}))).status,401);
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions?tenant_id=foreign','GET',admin))).status,403);
 await assert.rejects(context(req('/tracking'),()=>pageGuard('/tracking')));
 assert.equal((await context(req('/tracking','GET',user),()=>pageGuard('/tracking'))).role,'user');
 await assert.rejects(context(req('/tracking','POST',user),()=>action(user.csrf)));
 await assert.rejects(context(req('/tracking','POST',admin),()=>action('wrong')));
 assert.deepEqual(await context(req('/tracking','POST',admin),()=>action(admin.csrf)),{authorized:true});
});
test('Canonical verification, body actor rejection, host/origin/CSRF, sub mapping and unchanged homepage',async()=>{
 const admin=await session('admin');const project=await createProject(admin,'isolated homepage');
 const missing={...project,project_id:'prj_'+randomUUID()};assert.equal((await createSub(admin,missing)).status,404);
 const bad=req('/api/v1/tracking/subscriptions','POST',admin,{project_id:project.project_id,actor:{role:'superadmin'},confirmed:true});assert.equal((await route.POST(bad)).status,422);
 const noCsrf=req('/api/v1/tracking/subscriptions','POST',admin,{});noCsrf.headers.delete('x-csrf-token');assert.equal((await route.POST(noCsrf)).status,403);
 const wrongOrigin=req('/api/v1/tracking/subscriptions','POST',admin,{});wrongOrigin.headers.set('origin','https://evil.invalid');assert.equal((await route.POST(wrongOrigin)).status,403);
 const wrongHost=req('/api/v1/tracking/subscriptions','POST',admin,{});wrongHost.headers.set('host','evil.invalid');assert.equal((await route.POST(wrongHost)).status,400);
 const created=await createSub(admin,project,'isolated');assert.equal(created.status,202);const cmd=(await created.json()).data;assert.match(cmd.subscription_id,/^sub_/);assert.notEqual(cmd.subscription_id,project.project_id);
 await until(async()=>(await state(cmd.subscription_id)).observed_state==='running');
 const row=await state(cmd.subscription_id);const removed=await route.DELETE(req('/api/v1/tracking/subscriptions/'+row.subscription_id,'DELETE',admin,undefined,{'if-match':`"rev-${row.revision}"`}));assert.equal(removed.status,202);
 await until(async()=>(await state(row.subscription_id)).observed_state==='absent');
 const unchanged=await projects.projectsRoute(req('/api/v1/projects/'+project.project_id,'GET',admin));assert.deepEqual((await unchanged.json()).data,project);
});
test('Actual B2 serialized outbox relay, lost ACK reconciles original ID with one provider add',async()=>{
 const relay=await import(pathToFileURL(join(preview,'apps/website/lib/outbox-relay.ts')));
 const command_id='cmd_'+randomUUID();const actor={user_id:'fixture-admin',tenant_id:'ikun-main',role:'superadmin'};
 const event={schema_version:1,event_id:'evt_'+randomUUID(),source:'hunter',event_type:'hunter.monitoring_requested',occurred_at:null,received_at:new Date().toISOString(),tenant_id:'ikun-main',project_id:null,correlation_id:randomUUID(),
  payload:{command_id,discovery_id:'synthetic-discovery',source_entity_key:'synthetic-source',confirmed:true,actor,project:{...fields,name:'B2 to Tracking'},x_user_id:'99887',x_handle:'b2_wire'}};
 const accepted=await projects.ipc({operation:'ingest',source:'hunter',request_id:randomUUID(),body:event});assert.equal(accepted.status,200);
 const wire=[];const bridge=createServer(async(request,response)=>{let body='';for await(const chunk of request)body+=chunk;wire.push({method:request.method,headers:request.headers,body});const result=await fetch(endpoint+request.url,{method:request.method,headers:request.headers,...(request.method==='POST'?{body}:{})});const text=await result.text();if(request.method==='POST'){response.destroy();return;}response.writeHead(result.status,{'content-type':'application/json'});response.end(text);});
 await new Promise(r=>bridge.listen(0,'127.0.0.1',r));
 try{const config={origin:'http://127.0.0.1:'+bridge.address().port,token};await relay.relayOnce(config,command_id);await relay.relayOnce(config,command_id);
  assert.deepEqual(wire.map(r=>r.method),['POST','GET']);assert.equal(wire[0].headers['idempotency-key'],undefined);assert.equal(wire[0].headers['if-match'],undefined);
  const sent=JSON.parse(wire[0].body);assert.equal(sent.command_id,command_id);assert.equal(sent.expected_revision,null);assert.equal(sent.payload.confirmed,true);
  const remote=(await(await internal('commands/'+command_id)).json()).data;assert.match(remote.subscription_id,/^sub_/);
  const recorded=await projects.ipc({operation:'command',principal:actor,target:command_id,request_id:randomUUID()});assert.equal(recorded.status,200);assert.equal((await recorded.json()).data.subscription_id,remote.subscription_id);
 }finally{bridge.closeAllConnections();await new Promise(r=>bridge.close(r));}
});
test('SSE standard envelope/replay and quiet revocation cancel the real Tracking upstream',async()=>{
 const admin=await session('admin'),user=await session('user');
 const request=req('/api/v1/tracking/events','GET',user);const response=await eventsRoute.GET(request);assert.equal(response.status,200);const reader=response.body.getReader();
 const block=await eventBlock(reader);const data=block.match(/data: (.+)/);assert.ok(data);assert.deepEqual(Object.keys(JSON.parse(data[1])).sort(),['data','request_id']);
 await new Promise(r=>setTimeout(r,5500));assert.equal((await(await fixture('state')).json()).active_streams,1);
 assert.equal((await auth.handle(req('/api/v1/auth/logout','POST',user,{}))).status,200);
 let done=false;for(let i=0;i<10;i++){const part=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('SSE_REVOCATION')),3000))]);if(part.done){done=true;break;}}assert.equal(done,true);await until(async()=>(await(await fixture('state')).json()).active_streams===0);
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,401);
 const active=await session('user');const replay=await eventsRoute.GET(req('/api/v1/tracking/events','GET',active));const r=replay.body.getReader();const text=await eventBlock(r);const eventId=text.match(/id: (evt_[^\n]+)/)?.[1];await r.cancel();assert.ok(eventId);
 const resumed=await eventsRoute.GET(req('/api/v1/tracking/events','GET',active,undefined,{'last-event-id':eventId}));const rr=resumed.body.getReader();const next=new TextDecoder().decode((await rr.read()).value);assert.ok(!next.includes('id: '+eventId+'\n'));await rr.cancel();await until(async()=>(await(await fixture('state')).json()).active_streams===0);
});
test('Disabled, reset, seven-day expiry and rotated B1 cookies are rejected in actual Tracking handler',async()=>{
 let user=await session('user');local.setEnabled('user',false);assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,401);local.setEnabled('user',true);
 user=await session('user');local.db.prepare('UPDATE auth_sessions SET created_at=created_at-604801 WHERE user_id=(SELECT id FROM auth_users WHERE username=?)').run('user');assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,401);
 user=await session('user');await local.reset('user','Synthetic-B3-Reset-482!');assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,401);
 const login=await local.login('user','Synthetic-B3-Reset-482!');await local.changePassword(login.actor,'Synthetic-B3-Reset-482!',password);
 user=await session('user');const other=await session('user');const rotated=await auth.handle(req('/api/v1/auth/password','POST',user,{current_password:password,new_password:'Synthetic-B3-Rotated-849!'}));assert.equal(rotated.status,200);
 assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',user))).status,401);assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',other))).status,401);
 const cookie=rotated.headers.get('set-cookie').split(';')[0];assert.equal((await route.GET(req('/api/v1/tracking/subscriptions','GET',{cookie,csrf:''}))).status,200);
});

test('Public command gateway reconciles direct Tracking commands after a genuine Projects 404',async()=>{
 const admin=await session('admin');const project=await createProject(admin,'Public reconcile');
 const response=await createSub(admin,project,'public_recon');assert.equal(response.status,202);const receipt=(await response.json()).data;
 const {GET}=await import(pathToFileURL(join(preview,'apps/website/app/api/v1/commands/[id]/route.ts')));
 const checked=await GET(req('/api/v1/commands/'+receipt.command_id,'GET',admin));assert.equal(checked.status,200);
 const value=(await checked.json()).data;assert.equal(value.command_id,receipt.command_id);assert.equal(value.subscription_id,receipt.subscription_id);
});

test('Concurrent refresh waits for a fresh snapshot, coalesces bursts, and recovers after failure',async()=>{
 const {coalescedRefresh}=await import(pathToFileURL(join(preview,'apps/website/lib/coalesced-refresh.ts')));
 let version=1,active=0,maximum=0;const seen=[],releases=[];
 const refresh=coalescedRefresh(async()=>{active++;maximum=Math.max(maximum,active);seen.push(version);await new Promise(resolve=>releases.push(resolve));active--;});
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 const first=refresh();await tick();version=2;const second=refresh();for(let i=0;i<20;i++)assert.equal(refresh(),second);assert.equal(seen.length,1);
 releases.shift()();await first;await tick();assert.deepEqual(seen,[1,2]);version=3;const third=refresh();releases.shift()();await second;await tick();assert.deepEqual(seen,[1,2,3]);releases.shift()();await third;assert.equal(maximum,1);
 let attempts=0;const failing=coalescedRefresh(async()=>{if(++attempts===1)throw Error('synthetic read failure');});const rejected=failing();const recovered=failing();await assert.rejects(rejected);await recovered;assert.equal(attempts,2);
});

test('Actual B1 + frozen B2 UDS rating catalog + Tracking profile globally filter, count and invalidate pages',async()=>{
 const admin=await session('admin'),projectsList=[],subs=[];
 for(let index=0;index<8;index++){
  const project=await createProject(admin,'C03 fixture '+index,{rating:['S','A','B','S','A','B','C',null][index]});projectsList.push(project);
  const accepted=await createSub(admin,project,'c03fixture'+index);assert.equal(accepted.status,202);const value=(await accepted.json()).data;subs.push(value.subscription_id);
  await until(async()=>(await state(value.subscription_id)).observed_state==='running');
  const content={id:String(10000+index),text:'C03 正文 '+index,createdAt:new Date().toISOString(),userScreenName:'c03fixture'+index,isReply:false,isQuote:index===3};
  assert.equal((await fixture('emit',{username:'c03fixture'+index,content})).status,200);
 }
 const path='/api/v1/tracking/latest?profile=published-v1&q=C03%20fixture&limit=2';
 let response;await until(async()=>{response=await route.GET(req(path,'GET',admin));if(!response.ok)return false;const d=await response.clone().json();return d.data.matched_total===6;});
 let result=(await response.json()).data;assert.equal(result.matched_total,6);assert.deepEqual(result.activity_counts_by_rating,{S:2,A:2,B:2});assert.equal(result.excluded.C,1);assert.equal(result.excluded.unrated,1);
 const all=[...result.items],firstCursor=result.next_cursor;while(result.next_cursor){const next=await route.GET(req(path.replace('limit=2','limit=1')+'&cursor='+encodeURIComponent(result.next_cursor),'GET',admin));assert.equal(next.status,200);result=(await next.json()).data;all.push(...result.items);}
 assert.equal(new Set(all.map(item=>item.activity_id)).size,6);assert.ok(all.some(item=>item.tweet_kind==='quote'));assert.ok(all.every(item=>item.notes==='subscription note first'));
 const first=await route.GET(req(path+'&ratings=S','GET',admin));const onlyS=(await first.json()).data;assert.equal(onlyS.matched_total,2);assert.ok(onlyS.items.every(item=>item.rating==='S'));
 assert.equal((await route.GET(req(path+'&q=different&cursor='+encodeURIComponent(firstCursor),'GET',admin))).status,422);
 const project=projectsList[0];const updated=await projects.projectsRoute(req('/api/v1/projects/'+project.project_id,'PATCH',admin,{rating:'B'},{'if-match':`"rev-${project.revision}"`}));assert.equal(updated.status,200);
 const stale=await route.GET(req(path+'&cursor='+encodeURIComponent(firstCursor),'GET',admin));assert.equal(stale.status,409);
 const current=await route.GET(req(path,'GET',admin));assert.equal(current.status,200);assert.deepEqual((await current.json()).data.activity_counts_by_rating,{S:1,A:2,B:3});
 await local.create('feedreader',initial);const login=await local.login('feedreader',initial);await local.changePassword(login.actor,initial,password);const user=await session('feedreader');assert.equal((await route.GET(req(path,'GET',user))).status,200);
});

test('Same authenticated view handles ten refreshes and filters during real WSS burst without self-exhaustion',async()=>{
 const admin=await session('admin'),view='qv1_'+randomUUID();
 for(let index=0;index<10;index++)await fixture('emit',{username:'c03fixture0',content:{id:String(200000+index),text:'C03 burst '+index,createdAt:new Date().toISOString(),userScreenName:'c03fixture0',isReply:false,isQuote:false}});
 for(let index=0;index<10;index++){
  const path='/api/v1/tracking/latest?profile=published-v1&limit=1&q=C03%20fixture&ratings='+['S,A,B','S','A','B'][index%4];
  const response=await route.GET(req(path,'GET',admin,undefined,{'x-tracking-query-view':view}));assert.equal(response.status,200);assert.ok((await response.json()).data.matched_total>=1);
 }
 assert.equal((await route.GET(req('/api/v1/tracking/latest?profile=published-v1','GET',admin,undefined,{'x-tracking-query-view':'invalid'}))).status,422);
});
