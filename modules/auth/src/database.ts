import {chmodSync,existsSync,lstatSync,mkdirSync,openSync,closeSync} from 'node:fs';
import {join,parse,resolve} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes} from 'node:crypto';
import type {AuthConfig} from './config.js';
import {FOUNDATION_SQL,FOUNDATION_CHECKSUM,MIGRATION_SQL,MIGRATION_CHECKSUM,LEGACY_CHECKSUM} from './schema.js';
export const APP_ID=0x494b0204;
function noLinks(path:string) {
  let current=parse(path).root;
  for(const part of path.slice(current.length).split('/')) {
    if(!part) continue;current=join(current,part);
    if(existsSync(current)&&lstatSync(current).isSymbolicLink()) throw new Error('AUTH_SYMLINK_REJECTED');
  }
  if(existsSync(path)&&lstatSync(path).isFile()&&lstatSync(path).nlink!==1) throw new Error('AUTH_FILE_ALIAS_REJECTED');
}
const has=(db:DatabaseSync,name:string)=>Boolean(db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?").get(name));
function foundation(db:DatabaseSync) {
  if(db.prepare('PRAGMA application_id').get()?.application_id!==APP_ID ||
     db.prepare('SELECT store_name FROM _store_identity WHERE singleton=1').get()?.store_name!=='auth')
    throw new Error('AUTH_FOREIGN_DATABASE_REJECTED');
  const columns=db.prepare('PRAGMA table_info(_schema_migrations)').all().map(row=>String(row.name));
  if(!['version','name','applied_at'].every(c=>columns.includes(c))||columns.some(c=>!['version','name','applied_at','checksum'].includes(c)))
    throw new Error('AUTH_METADATA_REJECTED');
  const versions=db.prepare('SELECT version,name FROM _schema_migrations ORDER BY version').all();
  if(versions[0]?.version!==1||versions[0]?.name!=='foundation'||versions.length>2||
    (versions[1]&&(versions[1].version!==2||versions[1].name!=='auth_accounts_v1'))||
    Number(db.prepare('PRAGMA user_version').get()?.user_version)>2) throw new Error('AUTH_UNSUPPORTED_VERSION');
  if(has(db,'_migration_checksums')&&db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=1').get()?.sha256!==FOUNDATION_CHECKSUM)
    throw new Error('AUTH_FOUNDATION_CHECKSUM_MISMATCH');
  return Number(versions.at(-1)?.version);
}
const expected:Record<string,string[]>={
  auth_users:['id','username','password_hash','role','enabled','version','must_change_password','created_at','updated_at'],
  auth_sessions:['token_hash','user_id','csrf_token','version','created_at','last_seen','expires_at'],
  auth_login_limits:['key','attempts','expires_at'],auth_audit:['id','actor_id','target_id','action','at'],
  auth_idempotency:['actor_id','route','key','body_hash','response','expires_at'],
  auth_migration_checksums:['version','checksum'],auth_site_scope:['singleton','tenant_id'],auth_metadata:['key','value']};
export function verifyAuthMetadata(db:DatabaseSync,cfg:AuthConfig):void {
  if(foundation(db)!==2) throw new Error('AUTH_MIGRATION_REQUIRED');
  if(!has(db,'_migration_checksums')||db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=2').get()?.sha256!==MIGRATION_CHECKSUM)
    throw new Error('AUTH_MIGRATION_CHECKSUM_MISMATCH');
  for(const [name,columns] of Object.entries(expected)) {
    const actual=db.prepare(`PRAGMA table_info(${name})`).all().map(row=>String(row.name));
    if(JSON.stringify(actual)!==JSON.stringify(columns)) throw new Error('AUTH_SCHEMA_MISMATCH');
  }
  const legacy=db.prepare('SELECT checksum FROM auth_migration_checksums WHERE version=2').get();
  if(legacy&&legacy.checksum!==LEGACY_CHECKSUM) throw new Error('AUTH_LEGACY_CHECKSUM_MISMATCH');
  if(db.prepare('SELECT tenant_id FROM auth_site_scope WHERE singleton=1').get()?.tenant_id!==cfg.tenantId)
    throw new Error('AUTH_SCOPE_MISMATCH');
  if(!/^[a-f0-9]{64}$/.test(String(db.prepare("SELECT value FROM auth_metadata WHERE key='cursor_key'").get()?.value)))
    throw new Error('AUTH_CURSOR_KEY_MISSING');
}
function paths(cfg:AuthConfig) {
  const directory=join(resolve(cfg.dataRoot),'auth'),path=join(directory,'auth.db');
  for(const p of [directory,path,path+'-wal',path+'-shm']) noLinks(p);
  if(existsSync(path)&&!lstatSync(path).isFile()) throw new Error('AUTH_FILE_ALIAS_REJECTED');
  return {directory,path};
}
export function inspectAuthDatabase(cfg:AuthConfig):boolean {
  const {path}=paths(cfg);if(!existsSync(path)) throw new Error('AUTH_MIGRATION_REQUIRED');
  const db=new DatabaseSync(path,{readOnly:true,timeout:5000});
  try {verifyAuthMetadata(db,cfg);return true;} finally {db.close();}
}
/** Exactly one auth writer, explicit migration; runtime and readiness never run DDL. */
export function database(cfg:AuthConfig,migrate=false):DatabaseSync {
  const {directory,path}=paths(cfg);
  if(!existsSync(path)&&!migrate) throw new Error('AUTH_MIGRATION_REQUIRED');
  if(existsSync(path)) {
    const check=new DatabaseSync(path,{readOnly:true,timeout:5000});
    try {foundation(check);if(!migrate) verifyAuthMetadata(check,cfg);} finally {check.close();}
  } else {mkdirSync(directory,{recursive:true,mode:0o700});closeSync(openSync(path,'wx',0o600));}
  const db=new DatabaseSync(path,{timeout:5000});
  try {
    db.exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA synchronous=FULL;');
    if(!migrate) return db;
    chmodSync(directory,0o700);chmodSync(path,0o600);db.exec('PRAGMA journal_mode=WAL; BEGIN IMMEDIATE;');
    if(db.prepare('PRAGMA application_id').get()?.application_id===0) {
      db.exec(`PRAGMA application_id=${APP_ID};${FOUNDATION_SQL}`);
      db.prepare('INSERT INTO _store_identity(singleton,store_name) VALUES(1,?)').run('auth');
      db.prepare("INSERT INTO _schema_migrations(version,name,applied_at) VALUES(1,'foundation',?)").run(new Date().toISOString());
    }
    const version=foundation(db);
    db.exec('CREATE TABLE IF NOT EXISTS _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL) STRICT;');
    db.prepare('INSERT OR IGNORE INTO _migration_checksums(version,sha256) VALUES(1,?)').run(FOUNDATION_CHECKSUM);
    if(version===1) {
      db.exec(MIGRATION_SQL);
      db.prepare('INSERT INTO auth_site_scope(singleton,tenant_id) VALUES(1,?)').run(cfg.tenantId);
      const extra=db.prepare('PRAGMA table_info(_schema_migrations)').all().some(r=>r.name==='checksum');
      const now=new Date().toISOString();
      if(extra) db.prepare("INSERT INTO _schema_migrations(version,name,applied_at,checksum) VALUES(2,'auth_accounts_v1',?,?)").run(now,MIGRATION_CHECKSUM);
      else db.prepare("INSERT INTO _schema_migrations(version,name,applied_at) VALUES(2,'auth_accounts_v1',?)").run(now);
    } else if(!db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=2').get()) {
      if(db.prepare('SELECT checksum FROM auth_migration_checksums WHERE version=2').get()?.checksum!==LEGACY_CHECKSUM)
        throw new Error('AUTH_LEGACY_CHECKSUM_MISMATCH');
      // Preserve every legacy row/hash; reconcile only through explicit migrate.
      db.exec('CREATE TABLE auth_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;');
    } else {verifyAuthMetadata(db,cfg);db.exec('COMMIT');return db;}
    db.prepare('INSERT INTO auth_metadata(key,value) VALUES(?,?)').run('cursor_key',randomBytes(32).toString('hex'));
    db.prepare('INSERT INTO _migration_checksums(version,sha256) VALUES(2,?)').run(MIGRATION_CHECKSUM);
    db.exec('PRAGMA user_version=2;');verifyAuthMetadata(db,cfg);db.exec('COMMIT');return db;
  } catch(error) {if(db.isTransaction) db.exec('ROLLBACK');db.close();throw error;}
}
