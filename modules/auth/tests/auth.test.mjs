import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync,statSync,mkdirSync,symlinkSync,linkSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {AuthStore} from '../dist/src/store.js';
import {LocalAccounts} from '../dist/src/local.js';
import {AuthHttp} from '../dist/src/http.js';
import {config} from '../dist/src/config.js';
import {verifyPassword} from '../dist/src/security.js';
import {fixture,user,req,origin,initial,password,changed} from './helpers.mjs';

for(const path of ['/','/hunter','/tracking','/api/v1/projects','/api/v1/auth/me'])
 test(`anonymous denied ${path}`,()=>fixture(async e=>{
  const denied=e.api.gate(req(path));assert.equal(denied.status,path.startsWith('/api/')?401:303);
 }));
for(const method of ['POST','PUT','PATCH','DELETE'])
 test(`user denied business ${method}, callback not executed`,()=>fixture(async e=>{
  const {logged}=await user(e);let called=false;
  const response=await e.api.business(req('/api/v1/projects',method,{},logged),()=>{called=true;return Response.json({});});
  assert.equal(response.status,403);assert.equal(called,false);
 }));

test('user reads three business pages and audited APIs; unknown and Hunter config denied',()=>fixture(async e=>{
 const {logged}=await user(e);
 for(const path of ['/','/hunter','/tracking','/api/v1/projects'])assert.equal(e.api.gate(req(path,'GET',undefined,logged)),null);
 for(const path of ['/api/v1/unknown','/api/v1/hunter/accounts'])assert.equal(e.api.gate(req(path,'GET',undefined,logged)).status,403);
}));
test('admin business writes use fresh frozen principal, client role is never authority',()=>fixture(async e=>{
 let count=0;const response=await e.api.business(req('/api/v1/projects','POST',{},e.root),p=>{
  count++;assert.ok(Object.isFrozen(p));assert.equal(p.role,'superadmin');assert.equal(p.tenant_id,'ikun-main');return Response.json({ok:true});});
 assert.equal(response.status,200);assert.equal(count,1);
 assert.equal((await e.api.business(req('/api/v1/projects','POST',{},undefined,{'x-role':'superadmin','x-user':e.root.actor.id}),()=>{throw Error('must not run');})).status,401);
}));
for(const path of ['/auth/users','/api/v1/auth/users','/api/v1/auth/users/usr_example','/api/v1/auth/users/usr_example/reset-password'])
 test(`removed account surface ${path} is unavailable even to admin`,()=>fixture(async e=>{
  for(const method of ['GET','POST','PATCH','DELETE']){
   const r=req(path,method,method==='GET'?undefined:{},e.root);
   assert.equal(e.api.gate(r).status,404);assert.equal((await e.api.handle(r)).status,404);
  }
 }));
test('registration unavailable and me capabilities never advertise remote user management',()=>fixture(async e=>{
 assert.equal((await e.api.handle(req('/api/v1/auth/register','POST',{},e.root))).status,404);
 const data=(await (await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root))).json()).data;
 assert.equal(data.capabilities.can_manage_users,false);assert.equal(data.capabilities.can_edit_projects,true);
 assert.ok(!JSON.stringify(data).includes(e.root.token));
}));

test('bootstrap admin and new users must change initial password on server before business',async()=>{
 const dir=mkdtempSync('/private/tmp/ikun-initial-');const store=new LocalAccounts(config({dataRoot:dir,origin,secure:false}),true);
 try {await store.bootstrap('first_admin',initial);const first=await store.login('first_admin',initial);const api=new AuthHttp(store);
  assert.equal(first.actor.must_change_password,true);
  assert.equal(api.gate(req('/api/v1/projects','GET',undefined,first)).status,403);
  assert.equal(api.gate(req('/','GET',undefined,first)).headers.get('location'),origin+'/auth/password');
  assert.equal((await api.handle(req('/api/v1/auth/me','GET',undefined,first))).status,200);
  for(const capability of Object.values((await (await api.handle(req('/api/v1/auth/me','GET',undefined,first))).json()).data.capabilities))assert.equal(capability,false);
  assert.equal(api.gate(req('/auth/password','GET',undefined,first)),null);
 }finally{store.close();rmSync(dir,{recursive:true,force:true});}
});
test('local create is user only, duplicate bootstrap/create rejected',()=>fixture(async e=>{
 const created=await e.store.create('viewer',initial);assert.equal(created.role,'user');assert.equal(created.must_change_password,true);
 await assert.rejects(e.store.bootstrap('second_admin',initial),x=>x.status===409);
 await assert.rejects(e.store.create('viewer',initial),x=>x.status===409);
 const first=await e.store.login('viewer',initial);
 assert.equal(e.api.gate(req('/api/v1/projects','GET',undefined,first)).status,403);
}));
test('local disable/enable revokes all sessions and returns the same generic login failure',()=>fixture(async e=>{
 const {logged}=await user(e);const second=await e.store.login('viewer',password);
 e.store.setEnabled('viewer',false);e.store.setEnabled('viewer',false);
 for(const session of [logged,second])assert.throws(()=>e.store.authenticate(session.token),x=>x.status===401);
 const messages=[];for(const [name,pass] of [['viewer',password],['ghost',password],['root_admin','wrong']]){
  const response=await e.api.handle(req('/api/v1/auth/login','POST',{username:name,password:pass}));assert.equal(response.status,401);messages.push((await response.json()).error.message);
 }assert.equal(new Set(messages).size,1);
 e.store.setEnabled('viewer',true);assert.ok(await e.store.login('viewer',password));
}));
test('local reset revokes every device and forces change without automatically enabling user',()=>fixture(async e=>{
 const {logged}=await user(e),second=await e.store.login('viewer',password);
 await e.store.reset('viewer',changed);
 for(const s of [logged,second])assert.throws(()=>e.store.authenticate(s.token),x=>x.status===401);
 const reset=await e.store.login('viewer',changed);assert.equal(reset.actor.must_change_password,true);
 assert.equal(e.api.gate(req('/api/v1/projects','GET',undefined,reset)).status,403);
 e.store.setEnabled('viewer',false);await e.store.reset('viewer',initial);
 await assert.rejects(e.store.login('viewer',initial),x=>x.status===401);
}));
test('admin recovery needs no web session, revokes sessions and forces password change',()=>fixture(async e=>{
 const other=await e.store.login('root_admin',password);await e.store.reset('root_admin',changed,true);
 for(const s of [e.root,other])assert.throws(()=>e.store.authenticate(s.token),x=>x.status===401);
 const recovered=await e.store.login('root_admin',changed);assert.equal(recovered.actor.must_change_password,true);
 await user(e);await assert.rejects(e.store.reset('viewer',changed,true),x=>x.status===409);
}));
test('last active superadmin cannot be disabled; schema supports future multiple admins safely',()=>fixture(async e=>{
 assert.throws(()=>e.store.setEnabled('root_admin',false),x=>x.status===409);
 const {record}=await user(e);e.store.db.prepare("UPDATE auth_users SET role='superadmin',enabled=0 WHERE id=?").run(record.id);
 assert.throws(()=>e.store.setEnabled('viewer',true),x=>x.status===409);
 // Synthetic future-policy fixture only; production CLI has no role-changing command.
 e.store.db.prepare('UPDATE auth_users SET enabled=1 WHERE id=?').run(record.id);
 e.store.setEnabled('viewer',false);assert.throws(()=>e.store.setEnabled('root_admin',false),x=>x.status===409);
}));
test('local list uses a strict safe projection and audit contains no credentials',()=>fixture(async e=>{
 await user(e);const list=e.store.list();assert.equal(list.length,2);
 for(const row of list)assert.deepEqual(Object.keys(row).sort(),['enabled','must_change_password','revision','role','user_id','username']);
 const audit=JSON.stringify(e.store.db.prepare('SELECT * FROM auth_audit').all());
 for(const secret of [initial,password,e.root.token])assert.ok(!audit.includes(secret));
}));

test('own password requires current password, rotates token and CSRF, revokes every old device',()=>fixture(async e=>{
 const other=await e.store.login('root_admin',password);
 assert.equal((await e.api.handle(req('/api/v1/auth/password','POST',{current_password:'wrong',new_password:changed},e.root))).status,422);
 assert.ok(e.store.authenticate(other.token));
 const response=await e.api.handle(req('/api/v1/auth/password','POST',{current_password:password,new_password:changed},e.root));
 assert.equal(response.status,200);assert.deepEqual((await response.json()).data,{changed:true,reauthentication_required:false});
 const token=response.headers.get('set-cookie').split(';')[0].split('=')[1];assert.notEqual(token,e.root.token);
 const actor=e.store.authenticate(token);assert.notEqual(actor.csrf_token,e.root.actor.csrf_token);assert.equal(actor.must_change_password,false);
 for(const s of [e.root,other])assert.throws(()=>e.store.authenticate(s.token),x=>x.status===401);
 assert.equal(e.store.db.prepare('SELECT count(*) AS n FROM auth_sessions').get().n,1);
}));
test('user can change own password but cannot change someone else or add fields',()=>fixture(async e=>{
 const {logged}=await user(e);
 assert.equal((await e.api.handle(req('/api/v1/auth/password','POST',{current_password:password,new_password:changed,user_id:e.root.actor.id},logged))).status,422);
 const response=await e.api.handle(req('/api/v1/auth/password','POST',{current_password:password,new_password:changed},logged));assert.equal(response.status,200);
 assert.ok(e.store.authenticate(e.root.token));
}));
test('logout revokes current session immediately, other device survives; repeat logout is safe',()=>fixture(async e=>{
 const other=await e.store.login('root_admin',password);
 for(let i=0;i<2;i++){const response=await e.api.handle(req('/api/v1/auth/logout','POST',{},e.root));assert.equal(response.status,200);assert.ok(response.headers.get('set-cookie').includes('Max-Age=0'));}
 assert.throws(()=>e.store.authenticate(e.root.token),x=>x.status===401);assert.ok(e.store.authenticate(other.token));
}));
test('seven-day absolute boundary survives activity and restart, cannot be extended',()=>fixture(async e=>{
 const row=e.store.db.prepare('SELECT * FROM auth_sessions').get();assert.equal(row.expires_at-row.created_at,604800);
 for(let i=0;i<6;i++){e.advance(86400);assert.equal(e.api.gate(req('/','GET',undefined,e.root)),null);}
 e.advance(86399);assert.ok(e.store.authenticate(e.root.token,true));e.restart();assert.ok(e.store.authenticate(e.root.token));
 e.advance(1);assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root))).status,401);
 assert.equal(e.api.gate(req('/','GET',undefined,e.root)).status,303);
}));
test('configuration and server cap reject sessions longer than seven days',()=>fixture(async e=>{
 assert.throws(()=>config({...e.cfg,absoluteTtl:604801}),/MAXIMUM/);assert.throws(()=>config({...e.cfg,idleTtl:604801}),/MAXIMUM/);
 e.store.db.exec('UPDATE auth_sessions SET expires_at=expires_at+999999');e.advance(604800);assert.throws(()=>e.store.authenticate(e.root.token),x=>x.status===401);
}));
test('login rotation/session cap do not reuse tokens and persisted tokens remain hashed',()=>fixture(async e=>{
 const tokens=[];for(let i=0;i<6;i++)tokens.push((await e.store.login('root_admin',password)).token);
 assert.equal(new Set(tokens).size,6);assert.throws(()=>e.store.authenticate(tokens[0]),x=>x.status===401);
 e.restart();assert.ok(e.store.authenticate(tokens[5]));
 const rows=e.store.db.prepare('SELECT token_hash FROM auth_sessions').all();assert.equal(rows.length,5);for(const row of rows){assert.equal(row.token_hash.length,64);assert.ok(!tokens.includes(row.token_hash));}
}));

test('CSRF/Origin/Host and duplicate cookies rejected at actual API entry',()=>fixture(async e=>{
 for(const patch of [{'x-csrf-token':'wrong'},{origin:'https://evil.example'},{host:'evil.example'},{'x-http-method-override':'DELETE'}]){
  const r=req('/api/v1/auth/password','POST',{current_password:password,new_password:changed},e.root);for(const [k,v] of Object.entries(patch))r.headers.set(k,v);
  assert.ok([400,403,422].includes((await e.api.handle(r)).status));
 }
 const r=req('/api/v1/auth/me','GET',undefined,e.root);r.headers.append('cookie',r.headers.get('cookie'));assert.equal((await e.api.handle(r)).status,401);
}));
test('Server Action guard independently enforces role/CSRF/force-change without proxy',()=>fixture(async e=>{
 const post=s=>req('/','POST',{},s);
 assert.equal(e.api.serverAction(post(e.root),e.root.actor.csrf_token).role,'superadmin');
 const {logged}=await user(e);assert.throws(()=>e.api.serverAction(post(logged),logged.actor.csrf_token),x=>x.status===403);
 assert.throws(()=>e.api.serverAction(post(e.root),'fake'),x=>x.status===403);
 const cross=post(e.root);cross.headers.set('origin','https://evil.example');assert.throws(()=>e.api.serverAction(cross,e.root.actor.csrf_token),x=>x.status===403);
 await e.store.reset('root_admin',changed,true);const first=await e.store.login('root_admin',changed);assert.throws(()=>e.api.serverAction(post(first),first.actor.csrf_token),x=>x.status===403);
}));
test('login limiter survives restart and ignores fake forwarded IP',()=>fixture(async e=>{
 for(let i=0;i<3;i++)assert.equal((await e.api.handle(req('/api/v1/auth/login','POST',{username:'ghost',password:'wrong'},undefined,{'x-forwarded-for':`192.0.2.${i}`}))).status,401);
 e.restart();const r=await e.api.handle(req('/api/v1/auth/login','POST',{username:'ghost',password:'wrong'}));assert.equal(r.status,429);assert.ok(Number(r.headers.get('retry-after'))>0);
 e.advance(900);assert.equal((await e.api.handle(req('/api/v1/auth/login','POST',{username:'ghost',password:'wrong'}))).status,401);
},{accountAttempts:3}));
test('weak/oversized passwords and request bodies rejected without echo',()=>fixture(async e=>{
 for(const p of ['short','x'.repeat(129)])await assert.rejects(e.store.create('bad_user',p),x=>x.status===422);
 const r=await e.api.handle(req('/api/v1/auth/login','POST',{username:'root_admin',password:'secret'.repeat(4000)}));assert.equal(r.status,413);assert.ok(!(await r.text()).includes('secret'));
 const r2=await e.api.handle(req('/api/v1/auth/password','POST',{current_password:password,new_password:password},e.root));assert.equal(r2.status,422);
}));
test('native POST forms reject non-JSON safely; no credentials in redirects/responses',()=>fixture(async e=>{
 for(const path of ['/api/v1/auth/login','/api/v1/auth/password']){
  const r=req(path,'POST',{},e.root);r.headers.set('content-type','application/x-www-form-urlencoded');
  const response=await e.api.handle(r);assert.equal(response.status,415);assert.equal(response.headers.get('location'),null);assert.ok(!(await response.text()).includes(password));
 }
}));
test('production cookie flags, seven-day Max-Age and private cache',async()=>{
 const dir=mkdtempSync('/private/tmp/ikun-cookie-');const store=new LocalAccounts(config({dataRoot:dir}),true);
 try{await store.bootstrap('admin_root',initial);const api=new AuthHttp(store);const response=await api.handle(new Request('https://ikun.ca/api/v1/auth/login',{method:'POST',headers:{host:'ikun.ca',origin:'https://ikun.ca','content-type':'application/json'},body:JSON.stringify({username:'admin_root',password:initial})}));
  assert.equal(response.status,200);for(const flag of ['__Host-ikun_session=','HttpOnly','Secure','SameSite=Strict','Max-Age=604800','Path=/'])assert.ok(response.headers.get('set-cookie').includes(flag));
  assert.ok(!response.headers.get('set-cookie').includes('Domain='));assert.match(response.headers.get('cache-control'),/no-store/);
 }finally{store.close();rmSync(dir,{recursive:true,force:true});}
});
test('Argon2id parameters, private database permissions and no raw tokens',()=>fixture(async e=>{
 const row=e.store.db.prepare('SELECT password_hash FROM auth_users').get();assert.match(row.password_hash,/^\$argon2id\$v=19\$m=65536,t=3,p=1\$/);assert.ok(await verifyPassword(row.password_hash,password));
 assert.equal(statSync(join(e.dir,'auth/auth.db')).mode&0o777,0o600);assert.equal(statSync(join(e.dir,'auth')).mode&0o777,0o700);
}));
test('CLI rejects pipes, password/role arguments and unsafe initialization before DB creation',()=>{
 for(const args of [['create','--username','viewer'],['bootstrap','--username','admin'],['create','--username','viewer','--role','superadmin'],['bootstrap','--username','admin','--password',password],['recover-admin','--username','admin'],['disable','--username','viewer'],['enable','--username','viewer'],['list']]){
  const dir=mkdtempSync('/private/tmp/ikun-cli-pipe-');try{const r=spawnSync(process.execPath,['modules/auth/dist/src/cli.js',...args],{input:password,encoding:'utf8',env:{...process.env,DATA_ROOT:dir}});assert.equal(r.status,1);assert.ok(!(r.stdout+r.stderr).includes(password));assert.throws(()=>statSync(join(dir,'auth/auth.db')));}finally{rmSync(dir,{recursive:true,force:true});}
 }
});
test('database isolation rejects a business database and filesystem aliases',()=>{
 const dir=mkdtempSync('/private/tmp/ikun-isolation-');const cfg=config({dataRoot:dir,origin,secure:false});mkdirSync(join(dir,'auth'));
 try{const path=join(dir,'auth/auth.db');let db=new DatabaseSync(path);db.exec('CREATE TABLE projects(id TEXT)');db.close();const before=readFileSync(path);assert.throws(()=>new AuthStore(cfg,true));assert.deepEqual(readFileSync(path),before);rmSync(path);
  const source=join(dir,'foreign.db');db=new DatabaseSync(source);db.close();symlinkSync(source,path);assert.throws(()=>new AuthStore(cfg,true));rmSync(path);linkSync(source,path);assert.throws(()=>new AuthStore(cfg,true));
 }finally{rmSync(dir,{recursive:true,force:true});}
});
for(const operation of ['disable','reset','password','expire','database-failure'])
 test(`SSE quiet revocation ${operation} closes and cancels upstream`,()=>fixture(async e=>{
  const {logged}=await user(e);let cancelled=false;
  const upstream=new Response(new ReadableStream({cancel(){cancelled=true;}}),{headers:{'content-type':'text/event-stream'}});
  const result=await e.api.business(req('/api/v1/projects','GET',undefined,logged),()=>upstream);const reader=result.body.getReader();
  if(operation==='disable')e.store.setEnabled('viewer',false);
  if(operation==='reset')await e.store.reset('viewer',changed);
  if(operation==='password')await e.store.changePassword(logged.actor,password,changed);
  if(operation==='expire')e.advance(604800);
  if(operation==='database-failure')e.store.db.exec('DROP TABLE auth_sessions');
  assert.equal((await reader.read()).done,true);assert.equal(cancelled,true);
 }));
test('scope headers/query cannot grant access',()=>fixture(async e=>{
 for(const header of ['x-tenant','x-tenant-id','x-scope'])assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root,{[header]:'other'}))).status,403);
 assert.equal(e.api.gate(req('/api/v1/projects?tenant_id=other','GET',undefined,e.root)).status,403);
}));

test('password session creation failure rolls back password/version and preserves old sessions',()=>fixture(async e=>{
 const before=e.store.db.prepare('SELECT password_hash,version FROM auth_users WHERE username=?').get('root_admin');
 e.store.db.exec("CREATE TRIGGER refuse_new_session BEFORE INSERT ON auth_sessions BEGIN SELECT RAISE(ABORT,'test rollback'); END");
 await assert.rejects(e.store.changePassword(e.root.actor,password,changed));
 assert.deepEqual(e.store.db.prepare('SELECT password_hash,version FROM auth_users WHERE username=?').get('root_admin'),before);
 assert.ok(e.store.authenticate(e.root.token));
}));
test('concurrent local bootstrap creates exactly one superadmin',async()=>{
 const dir=mkdtempSync('/private/tmp/ikun-bootstrap-race-');const cfg=config({dataRoot:dir,origin,secure:false});
 const first=new LocalAccounts(cfg,true),second=new LocalAccounts(cfg);
 try{const result=await Promise.allSettled([first.bootstrap('admin_first',initial),second.bootstrap('admin_second',initial)]);
  assert.equal(result.filter(x=>x.status==='fulfilled').length,1);assert.equal(first.list().filter(x=>x.role==='superadmin').length,1);
 }finally{first.close();second.close();rmSync(dir,{recursive:true,force:true});}
});
test('concurrent local resets cannot silently overwrite a newer password',()=>fixture(async e=>{
 await user(e);const result=await Promise.allSettled([e.store.reset('viewer',changed),e.store.reset('viewer',initial)]);
 assert.equal(result.filter(x=>x.status==='fulfilled').length,1);
 assert.equal(result.filter(x=>x.status==='rejected'&&x.reason.status===409).length,1);
}));
test('SSE rechecks before delivering a data chunk after revocation',()=>fixture(async e=>{
 const {logged}=await user(e);let streamController,cancelled=false;
 const upstream=new Response(new ReadableStream({start(c){streamController=c;},cancel(){cancelled=true;}}),{headers:{'content-type':'text/event-stream'}});
 const result=await e.api.business(req('/api/v1/projects','GET',undefined,logged),()=>upstream);
 const read=result.body.getReader().read();e.store.setEnabled('viewer',false);
 streamController.enqueue(new TextEncoder().encode('data: must-not-leak\n\n'));
 assert.equal((await read).done,true);assert.equal(cancelled,true);
}));
test('new CLI account cannot skip force-change via a forged role or a Server Action',()=>fixture(async e=>{
 await e.store.create('new_user',initial);const first=await e.store.login('new_user',initial);
 const request=req('/','POST',{},first,{'x-role':'superadmin'});
 assert.throws(()=>e.api.serverAction(request,first.actor.csrf_token),x=>x.status===403);
}));
