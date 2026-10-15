/** Actual production Next bundles; run the entire server lifetime under the shared heavy lock. */
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync, realpathSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createServer} from 'node:net';
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url)), preview=join(moduleRoot,'.b3/preview');
const python=join(moduleRoot,'.venv/bin/python'), root=realpathSync(mkdtempSync('/private/tmp/ik-b3-auth-'));
const logs=join(moduleRoot,'artifacts/b3/auth-next-'+Date.now());mkdirSync(logs,{recursive:true});
const {config}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/config.js')));
const {LocalAccounts}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/local.js')));
const {ManagedProjectsIpc,spawnManaged}=await import(pathToFileURL(join(preview,'packages/runtime/dist/index.js')));
const binding=JSON.parse(readFileSync(join(moduleRoot,'.b3/frozen-inputs-verified.json')));
const initial='Synthetic-Auth-Initial-451!', password='Synthetic-Auth-Password-551!', rotated='Synthetic-Auth-Rotated-651!';
const token='auth-next-private-tracking-direction-xxxxxxxxx', fixtureToken=randomUUID();
let local, manager, engine, website;const checks=[];
async function port(){const s=createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
const sitePort=await port(), trackingPort=await port(), origin='http://127.0.0.1:'+sitePort;
async function until(fn){for(let i=0;i<200;i++){try{if(await fn())return;}catch{}await new Promise(r=>setTimeout(r,50));}throw Error('AUTH_NEXT_CONDITION_TIMEOUT');}
async function http(path,session,method='GET',body){return fetch(origin+path,{method,redirect:'manual',signal:AbortSignal.timeout(10000),headers:{origin,'content-type':'application/json',...(session?{cookie:session.cookie,'x-csrf-token':session.csrf}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});}
async function login(name){const r=await http('/api/v1/auth/login',null,'POST',{username:name,password});assert.equal(r.status,200);return{cookie:r.headers.get('set-cookie').split(';')[0],csrf:(await r.json()).data.csrf_token};}
async function alternate(session){for(const path of ['/api/v1/projects?limit=1','/api/v1/tracking/subscriptions?limit=1','/api/v1/projects?limit=1','/api/v1/tracking/latest?limit=1']){const r=await http(path,session);assert.equal(r.status,200,path);await r.arrayBuffer();}}
async function denied(session,label){for(const path of ['/tracking','/']){const r=await http(path,session);assert.equal(r.status,303,label+' page '+path);assert.equal(new URL(r.headers.get('location'),origin).pathname,'/login');await r.arrayBuffer();}for(const path of ['/api/v1/projects?limit=1','/api/v1/tracking/subscriptions','/api/v1/tracking/latest']){const r=await http(path,session);assert.equal(r.status,401,label+' API '+path);const value=await r.json();assert.equal(value.error.code,'UNAUTHENTICATED');assert.equal(value.data,undefined);}checks.push({case:label,pages:303,apis:401});}
async function quietStream(session,mutation){const r=await http('/api/v1/events/stream',session);assert.equal(r.status,200);const reader=r.body.getReader();await reader.read();await mutation();let closed=false;const until=Date.now()+3500;while(Date.now()<until){const timer=AbortSignal.timeout(Math.max(1,until-Date.now()));const part=await Promise.race([reader.read(),new Promise((_,reject)=>timer.addEventListener('abort',()=>reject(Error('QUIET_SSE_NOT_REVOKED')),{once:true}))]);if(part.done){closed=true;break;}}assert.equal(closed,true);await reader.cancel().catch(()=>{});}
try{
 process.env.DATA_ROOT=root;process.env.IKUN_AUTH_ORIGIN=origin;process.env.IKUN_AUTH_DEV='1';
 local=new LocalAccounts(config({dataRoot:root,origin,secure:false}),true);await local.bootstrap('admin',initial);
 for(const name of ['admin','disabled','logout','changed','expired','reset']){if(name!=='admin')await local.create(name,initial);const result=await local.login(name,initial);await local.changePassword(result.actor,initial,password);}
 const entry=join(preview,'modules/projects/integration/ipc-entry.py');execFileSync(python,[entry,'--migrate','--database',join(root,'projects/projects.db')]);
 manager=new ManagedProjectsIpc({executable:python,args:[entry],cwd:join(preview,'modules/projects/candidate'),entry_path:entry,entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:binding.pins.projects},root);await manager.start(15000);
 const cfg=join(root,'tracking.json');writeFileSync(cfg,JSON.stringify({db_path:join(root,'tracking/tracking.db'),port:trackingPort,remote_enabled:true,dedicated_account:true,reconcile_seconds:.1,backfill_seconds:.2,request_interval:0,heartbeat_seconds:.1,heartbeat_timeout:.5}));
 execFileSync(python,['-m','tracking.cli','init','--config',cfg],{cwd:moduleRoot,env:{...process.env,DATA_ROOT:root}});
 engine=spawnManaged(python,[join(moduleRoot,'integration/tests/fixture-tracking.py'),cfg,fixtureToken],{cwd:moduleRoot,env:{PATH:process.env.PATH,TRACKING_API_TOKEN:token,IKUN_TRACKING_6551_TOKEN:'synthetic-auth-provider-not-real'},inheritOutput:true,graceMs:3000});
 await until(async()=>(await fetch('http://127.0.0.1:'+trackingPort+'/health/ready')).ok);
 website=spawnManaged(process.execPath,[join(preview,'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(sitePort)],{cwd:join(preview,'apps/website'),env:{PATH:process.env.PATH,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',DATA_ROOT:root,IKUN_AUTH_ORIGIN:origin,IKUN_AUTH_DEV:'1',TRACKING_API_TOKEN:token,TRACKING_API_URL:'http://127.0.0.1:'+trackingPort,IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha},inheritOutput:true,graceMs:5000});
 await until(async()=>(await fetch(origin+'/health/live')).ok);
 const admin=await login('admin');await alternate(admin);await denied(null,'anonymous-after-alternating-bundles');
 for(const name of ['disabled','logout','changed','expired','reset']){
  const session=await login(name);await alternate(session);
  await quietStream(session,async()=>{
   if(name==='disabled')local.setEnabled(name,false);
   if(name==='logout'){const r=await http('/api/v1/auth/logout',session,'POST',{});assert.equal(r.status,200);}
   if(name==='changed'){const r=await http('/api/v1/auth/password',session,'POST',{current_password:password,new_password:rotated});assert.equal(r.status,200);}
   if(name==='expired')local.db.prepare('UPDATE auth_sessions SET created_at=created_at-604801 WHERE user_id=(SELECT id FROM auth_users WHERE username=?)').run(name);
   if(name==='reset')await local.reset(name,rotated);
  });
  await denied(session,name);await alternate(admin);
 }
 const result={passed:true,checks,quiet_sse_revocation_cases:5,pins:binding.pins,preview_source_set_sha256:binding.preview_source_set_sha256,build_id:readFileSync(join(preview,'apps/website/.next/BUILD_ID'),'utf8').trim(),real_provider_calls:0};
 writeFileSync(join(logs,'receipt.json'),JSON.stringify(result,null,2));writeFileSync(join(moduleRoot,'artifacts/b3/auth-next-receipt-path.txt'),logs);console.log('B3_AUTH_NEXT_PASS '+logs);
}catch(error){writeFileSync(join(logs,'failure.json'),JSON.stringify({checks,message:String(error.stack||error)},null,2));throw error;}
finally{await website?.stop();await engine?.stop();await manager?.stop();local?.close();}
