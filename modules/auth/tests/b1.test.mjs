import assert from 'node:assert/strict';
import {test} from 'node:test';
import {randomUUID} from 'node:crypto';
import {mkdtempSync,mkdirSync,rmSync,readFileSync,copyFileSync} from 'node:fs';
import {join} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {AuthStore} from '../dist/src/store.js';
import {config} from '../dist/src/config.js';
import {APP_ID,inspectAuthDatabase} from '../dist/src/database.js';
import {FOUNDATION_SQL,FOUNDATION_CHECKSUM,MIGRATION_SQL,MIGRATION_CHECKSUM,LEGACY_SQL,LEGACY_CHECKSUM} from '../dist/src/schema.js';
import {hashPassword,digest} from '../dist/src/security.js';
import {fixture,origin,password} from './helpers.mjs';
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
