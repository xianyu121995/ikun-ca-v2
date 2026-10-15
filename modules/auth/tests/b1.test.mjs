import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,mkdirSync,readFileSync,copyFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {setTimeout as delay} from 'node:timers/promises';
import {config} from '../dist/src/config.js';
import {AuthStore} from '../dist/src/store.js';
import {AuthHttp} from '../dist/src/http.js';
import {APP_ID,inspectAuthDatabase} from '../dist/src/database.js';
import {FOUNDATION_SQL,FOUNDATION_CHECKSUM,LEGACY_SQL,LEGACY_CHECKSUM,MIGRATION_CHECKSUM} from '../dist/src/schema.js';
import {hashPassword,digest} from '../dist/src/security.js';
const origin='http://127.0.0.1:3600',password='b1-fictional-long-passphrase',changed='b1-fictional-new-passphrase';
async function fixture(fn){const dir=mkdtempSync('/private/tmp/ikun-auth-b1-');const cfg=config({dataRoot:dir,origin,secure:false});
  const store=new AuthStore(cfg,true),api=new AuthHttp(store,[/^\/api\/v1\/projects$/]);
  try{await store.bootstrap('root_admin',password);const root=await store.login('root_admin',password);await fn({dir,cfg,store,api,root});}
  finally{store.close();rmSync(dir,{recursive:true,force:true});}}
function req(path,method='GET',data,session,extra={}){const headers={host:new URL(origin).host,...extra};
  if(session){headers.cookie=`ikun_dev_session=${session.token}`;headers['x-csrf-token']=session.actor.csrf_token;}
  if(data!==undefined){headers.origin=origin;headers['content-type']='application/json';}
  return new Request(origin+path,{method,headers,...(data!==undefined?{body:JSON.stringify(data)}:{})});}
const mutation=(revision,key=randomUUID())=>({'if-match':`"rev-${revision}"`,'idempotency-key':key});
async function user(env,name='viewer',role='user'){
  const record=await env.store.createUser(env.root.actor,name,password,role,randomUUID());
  let logged=await env.store.login(name,password);
  await env.store.changePassword(logged.actor,password,changed);
  logged=await env.store.login(name,changed);return {record,logged};}
const keys=['can_edit_projects','can_manage_hunter','can_manage_tracking','can_manage_users'];
test('B1 AuthSessionV2 exact projection and server capabilities',()=>fixture(async e=>{
  for(const [session,allowed] of [[e.root,true],[(await user(e)).logged,false]]){
    const r=await e.api.handle(req('/api/v1/auth/me','GET',undefined,session));const {data}=await r.json();
    assert.deepEqual(Object.keys(data).sort(),['user_id','username','tenant_id','role','must_change_password','csrf_token','capabilities'].sort());
    assert.equal(data.tenant_id,'ikun-main');assert.deepEqual(data.capabilities,Object.fromEntries(keys.map(k=>[k,allowed])));
    assert.equal(r.headers.get('cache-control'),'no-store, private');assert.ok(r.headers.get('x-request-id'));
  }
}));
test('B1 forced-change superadmin has no capabilities',()=>fixture(async e=>{
  await e.store.createUser(e.root.actor,'new_admin',password,'superadmin',randomUUID());const session=await e.store.login('new_admin',password);
  const {data}=await (await e.api.handle(req('/api/v1/auth/me','GET',undefined,session))).json();
  assert.deepEqual(data.capabilities,Object.fromEntries(keys.map(k=>[k,false])));
  assert.equal(e.api.gate(req('/api/v1/projects','GET',undefined,session)).status,403);
}));
test('B1 users PageV2, signed cursor, restart, actor/limit/tamper/unknown field binding',()=>fixture(async e=>{
  await user(e,'alpha');await user(e,'bravo');
  const first=await (await e.api.handle(req('/api/v1/auth/users?limit=2','GET',undefined,e.root))).json();
  assert.equal(first.data.items.length,2);assert.ok(first.data.next_cursor);
  for(const item of first.data.items)assert.deepEqual(Object.keys(item).sort(),['user_id','username','role','enabled','must_change_password','revision','created_at','updated_at'].sort());
  const path='/api/v1/auth/users?limit=2&cursor='+encodeURIComponent(first.data.next_cursor);
  const second=await (await e.api.handle(req(path,'GET',undefined,e.root))).json();
  assert.equal(second.data.items.length,1);assert.equal(second.data.next_cursor,null);
  assert.equal(new Set([...first.data.items,...second.data.items].map(u=>u.user_id)).size,3);
  const reopened=new AuthStore(e.cfg);try{assert.equal(new AuthHttp(reopened).store.pageUsers(e.root.actor,2,first.data.next_cursor).items.length,1);}finally{reopened.close();}
  const {logged}=await user(e,'other_admin','superadmin');
  for(const path of ['/api/v1/auth/users?limit=101','/api/v1/auth/users?limit=1e2','/api/v1/auth/users?unknown=x',
    '/api/v1/auth/users?limit=2&cursor=invalid','/api/v1/auth/users?limit=1&cursor='+first.data.next_cursor])
    assert.equal((await e.api.handle(req(path,'GET',undefined,e.root))).status,422);
  assert.equal((await e.api.handle(req(path,'GET',undefined,logged))).status,422);
}));
test('B1 exact logout/password responses and no replacement session',()=>fixture(async e=>{
  let r=await e.api.handle(req('/api/v1/auth/password','POST',{current_password:password,new_password:changed},e.root));
  assert.deepEqual((await r.json()).data,{changed:true,reauthentication_required:true});assert.match(r.headers.get('set-cookie'),/Max-Age=0/);
  assert.throws(()=>e.store.authenticate(e.root.token));
  const next=await e.store.login('root_admin',changed);
  r=await e.api.handle(req('/api/v1/auth/logout','POST',{},next));assert.deepEqual((await r.json()).data,{logged_out:true});
  assert.deepEqual((await (await e.api.handle(req('/api/v1/auth/logout','POST',{},next))).json()).data,{logged_out:true});
  assert.equal((await e.api.handle(req('/api/v1/auth/logout','POST',{role:'superadmin'},next))).status,422);
}));
test('B1 reset accepts only new_password, DTO user_id and revokes all sessions',()=>fixture(async e=>{
  const {record,logged}=await user(e);const path=`/api/v1/auth/users/${record.id}/reset-password`;
  assert.equal((await e.api.handle(req(path,'POST',{password},e.root,mutation(2)))).status,422);
  const r=await e.api.handle(req(path,'POST',{new_password:password},e.root,mutation(2)));assert.equal(r.status,200);
  const {data}=await r.json();assert.equal(data.user_id,record.id);assert.equal(data.id,undefined);assert.ok(data.must_change_password);
  assert.throws(()=>e.store.authenticate(logged.token));
}));
for(const patch of [{role:'user'},{enabled:false},{must_change_password:true}])
 test(`B1 PATCH revocation ${JSON.stringify(patch)}`,()=>fixture(async e=>{
  const {record,logged}=await user(e,'second_admin','superadmin');
  const r=await e.api.handle(req(`/api/v1/auth/users/${record.id}`,'PATCH',patch,e.root,mutation(2)));
  assert.equal(r.status,200);assert.throws(()=>e.store.authenticate(logged.token));assert.equal((await r.json()).data.revision,3);
 }));
test('B1 PATCH whitelist, booleans and role validation',()=>fixture(async e=>{
  const id=e.root.actor.id;
  for(const patch of [{},{role:'admin'},{enabled:1},{must_change_password:'false'},{username:'renamed'},{tenant_id:'other'}])
    assert.equal((await e.api.handle(req(`/api/v1/auth/users/${id}`,'PATCH',patch,e.root,mutation(1)))).status,422);
}));
test('B1 concurrent last-admin downgrade/disable cannot remove both admins',()=>fixture(async e=>{
  const {record,logged}=await user(e,'second_admin','superadmin');
  const results=await Promise.allSettled([
    e.store.patchUser(e.root.actor,record.id,{role:'user'},2,randomUUID()),
    e.store.patchUser(logged.actor,e.root.actor.id,{enabled:false},1,randomUUID())]);
  assert.equal(results.filter(r=>r.status==='fulfilled').length,1);
  assert.equal(e.store.db.prepare("SELECT count(*) AS n FROM auth_users WHERE role='superadmin' AND enabled=1").get().n,1);
}));
test('B1 trusted principal/BFF gate never calls callback for fake client identity',()=>fixture(async e=>{
  let calls=0;const callback=p=>{calls++;assert.ok(Object.isFrozen(p));assert.deepEqual(p,{user_id:e.root.actor.id,tenant_id:'ikun-main',role:'superadmin'});return Response.json({ok:true});};
  const fake=req('/api/v1/projects','POST',{},undefined,{'x-role':'superadmin','x-user':e.root.actor.id,'x-tenant':'ikun-main'});
  assert.equal((await e.api.business(fake,callback)).status,401);assert.equal(calls,0);
  assert.equal((await e.api.business(req('/api/v1/projects','POST',{},e.root),callback)).status,200);assert.equal(calls,1);
  const {logged}=await user(e);assert.equal((await e.api.business(req('/api/v1/projects','POST',{},logged),callback)).status,403);assert.equal(calls,1);
}));
for(const operation of ['disable','reset','password','demote','expire','database-failure'])
 test(`B1 silent SSE closes/cancels on ${operation}`,()=>fixture(async e=>{
  const {record,logged}=await user(e,'stream_admin','superadmin');let cancelled=false;
  const response=await e.api.business(req('/api/v1/projects','GET',undefined,logged),()=>new Response(new ReadableStream({
    start(c){c.enqueue(new TextEncoder().encode('data: first\n\n'));},cancel(){cancelled=true;}}),{headers:{'content-type':'text/event-stream'}}));
  const reader=response.body.getReader();await reader.read();
  if(operation==='disable')await e.store.patchUser(e.root.actor,record.id,{enabled:false},2,randomUUID());
  if(operation==='reset')await e.store.resetPassword(e.root.actor,record.id,password,2,randomUUID());
  if(operation==='password')await e.store.changePassword(logged.actor,changed,password);
  if(operation==='demote')await e.store.patchUser(e.root.actor,record.id,{role:'user'},2,randomUUID());
  if(operation==='expire')e.store.db.prepare('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?').run(record.id);
  if(operation==='database-failure')e.store.db.exec('ALTER TABLE auth_sessions RENAME TO temporarily_unavailable_sessions');
  try{assert.ok((await Promise.race([reader.read(),delay(2500).then(()=>{throw new Error('SSE failed to close');})])).done);assert.ok(cancelled);}
  finally{if(operation==='database-failure')e.store.db.exec('ALTER TABLE temporarily_unavailable_sessions RENAME TO auth_sessions');}
 }));
test('B1 SSE checks immediately before each data chunk',()=>fixture(async e=>{
  let send,cancelled=false;
  const upstream=new Response(new ReadableStream({start(c){send=c;},cancel(){cancelled=true;}}),{headers:{'content-type':'text/event-stream'}});
  const reader=e.api.stream(req('/api/v1/projects','GET',undefined,e.root),upstream).body.getReader();
  const pending=reader.read();e.store.logout(e.root.actor);send.enqueue(new TextEncoder().encode('must-not-leak'));
  assert.ok((await pending).done);await delay(1);assert.ok(cancelled);
}));
function base(dir,extra=false){mkdirSync(join(dir,'auth'),{recursive:true});const db=new DatabaseSync(join(dir,'auth/auth.db'));
 db.exec(`PRAGMA application_id=${APP_ID};${FOUNDATION_SQL}`);db.prepare('INSERT INTO _store_identity(singleton,store_name) VALUES(1,?)').run('auth');
 db.prepare('INSERT INTO _schema_migrations(version,name,applied_at) VALUES(1,?,?)').run('foundation','2026-10-15T00:00:00Z');
 if(extra)db.exec('ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT');return db;}
test('B1 frozen Auth2 reconciliation preserves users, sessions, receipts and legacy checksum',async()=>{
 const dir=mkdtempSync('/private/tmp/ikun-auth-legacy-'),cfg=config({dataRoot:dir,origin,secure:false});let db=base(dir,true);
 try{db.exec(LEGACY_SQL);db.prepare('INSERT INTO auth_migration_checksums(version,checksum) VALUES(2,?)').run(LEGACY_CHECKSUM);
  db.prepare('INSERT INTO auth_site_scope(singleton,tenant_id) VALUES(1,?)').run('ikun-main');
  db.prepare('INSERT INTO _schema_migrations(version,name,applied_at,checksum) VALUES(2,?,?,?)').run('auth_accounts_v1','2026-10-15T00:00:00Z','preserve-this-column');
  const hash=await hashPassword(password),id='usr_'+randomUUID(),token='fictional-legacy-session';
  db.prepare('INSERT INTO auth_users(id,username,password_hash,role,enabled,version,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)')
   .run(id,'legacy_user',hash,'user',1,1,0,1800000000,1800000000);
  db.prepare('INSERT INTO auth_sessions(token_hash,user_id,csrf_token,version,created_at,last_seen,expires_at) VALUES(?,?,?,?,?,?,?)')
   .run(digest(token),id,'fictional-csrf',1,1800000000,1800000000,1800001000);
  db.prepare('INSERT INTO auth_idempotency(actor_id,route,key,body_hash,response,expires_at) VALUES(?,?,?,?,?,?)')
   .run(id,'keep-receipt',randomUUID(),hash,'{"preserved":true}',1800001000);
  const tables=['auth_users','auth_sessions','auth_idempotency','auth_migration_checksums','_schema_migrations'];
  const before=tables.map(t=>JSON.stringify(db.prepare(`SELECT * FROM ${t}`).all()));db.close();db=null;
  assert.throws(()=>new AuthStore(cfg),/CHECKSUM/);
  let store=new AuthStore(cfg,true,()=>1800000000);try{
    assert.equal(store.authenticate(token).id,id);for(const [index,t] of tables.entries())assert.equal(JSON.stringify(store.db.prepare(`SELECT * FROM ${t}`).all()),before[index]);
    assert.equal(store.db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=1').get().sha256,FOUNDATION_CHECKSUM);
    assert.equal(store.db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=2').get().sha256,MIGRATION_CHECKSUM);
  }finally{store.close();}
  store=new AuthStore(cfg,true,()=>1800000000);store.close();assert.ok(inspectAuthDatabase(cfg));
 }finally{db?.close();rmSync(dir,{recursive:true,force:true});}
});
test('B1 migration failure rolls back/preserves, backup recovers at a new path',()=>{
 const dir=mkdtempSync('/private/tmp/ikun-auth-rollback-'),cfg=config({dataRoot:dir,origin,secure:false});let db=base(dir);db.close();
 const backup=join(dir,'foundation.backup');copyFileSync(join(dir,'auth/auth.db'),backup);
 db=new DatabaseSync(join(dir,'auth/auth.db'));db.exec("CREATE TABLE auth_users(sentinel TEXT);INSERT INTO auth_users(sentinel) VALUES('preserved')");db.close();
 try{assert.throws(()=>new AuthStore(cfg,true));db=new DatabaseSync(join(dir,'auth/auth.db'));
  assert.equal(db.prepare('SELECT max(version) AS n FROM _schema_migrations').get().n,1);
  assert.equal(db.prepare('SELECT sentinel FROM auth_users').get().sentinel,'preserved');
  assert.equal(db.prepare("SELECT name FROM sqlite_master WHERE name='_migration_checksums'").get(),undefined);db.close();
  const recovered=join(dir,'recovered');mkdirSync(join(recovered,'auth'),{recursive:true});copyFileSync(backup,join(recovered,'auth/auth.db'));
  const store=new AuthStore(config({...cfg,dataRoot:recovered}),true);store.close();assert.ok(inspectAuthDatabase(config({...cfg,dataRoot:recovered})));
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('B1 readonly inspection cannot migrate or recreate missing auth DB',()=>{
 const dir=mkdtempSync('/private/tmp/ikun-auth-readiness-'),cfg=config({dataRoot:dir,origin,secure:false});
 try{assert.throws(()=>inspectAuthDatabase(cfg));let db=base(dir);const before=JSON.stringify(db.prepare('SELECT * FROM _schema_migrations').all());db.close();
  assert.throws(()=>inspectAuthDatabase(cfg));db=new DatabaseSync(join(dir,'auth/auth.db'));assert.equal(JSON.stringify(db.prepare('SELECT * FROM _schema_migrations').all()),before);
  assert.equal(db.prepare("SELECT name FROM sqlite_master WHERE name='auth_users'").get(),undefined);db.close();
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('B1 fixed scope and future SQLite versions fail closed',()=>fixture(async e=>{
 assert.throws(()=>config({...e.cfg,tenantId:'other'}),/SCOPE/);
 e.store.db.exec('PRAGMA user_version=3');assert.throws(()=>inspectAuthDatabase(e.cfg),/UNSUPPORTED_VERSION/);e.store.db.exec('PRAGMA user_version=2');
}));
test('B1 actual pinned B0 defaults reject Auth2; explicit readonly domain admission checks checksum/scope',async()=>{
 const manifest=JSON.parse(readFileSync(new URL('../test-results/b1-preview.json',import.meta.url)));
 const runtime=await import(new URL('file://'+join(manifest.preview,'packages/runtime/dist/index.js')));
 const dir=mkdtempSync('/private/tmp/ikun-auth-b0-policy-'),cfg=config({dataRoot:dir,origin,secure:false});
 try{
  const created=runtime.openStores('website',dir,{names:['auth']});runtime.closeStores(created);
  assert.throws(()=>new AuthStore(cfg),/AUTH_MIGRATION_REQUIRED/);
  const store=new AuthStore(cfg,true);store.close();
  assert.throws(()=>runtime.inspectStores('website',dir,{names:['auth']}),/UNSUPPORTED_SCHEMA_VERSION/);
  const handles=runtime.inspectStores('website',dir,{names:['auth'],maximumVersion:2});runtime.closeStores(handles);
  assert.ok(inspectAuthDatabase(cfg));
  const db=new DatabaseSync(join(dir,'auth/auth.db'));
  db.prepare('UPDATE _migration_checksums SET sha256=? WHERE version=2').run('wrong');db.close();
  assert.throws(()=>inspectAuthDatabase(cfg),/AUTH_MIGRATION_CHECKSUM_MISMATCH/);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('B1 cross-scope headers are rejected instead of becoming identity',()=>fixture(async e=>{
 for(const header of ['x-tenant','x-tenant-id','x-scope']) assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root,{[header]:'other'}))).status,403);
}));
