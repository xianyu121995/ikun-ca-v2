"""Private, restartable backups. PostgreSQL writes are confined to a new drill cluster."""
from contextlib import closing,contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import tempfile
import time
import uuid

class SafeFailure(RuntimeError):pass
def utc():return datetime.now(timezone.utc).isoformat()
def require(value,code):
 if not value:raise SafeFailure(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def private_dir(path):
 path=Path(path);path.mkdir(mode=0o700,parents=True,exist_ok=True);s=path.lstat()
 require(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'UNSAFE_OUTPUT_DIRECTORY');return path
def atomic(path,value):
 path=Path(path);data=value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
 temp=path.with_name(path.name+'.new-'+uuid.uuid4().hex)
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(temp,path)
def read_json(path):return json.loads(Path(path).read_text())
def artifact(path):
 path=Path(path);s=path.lstat();require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,'UNSAFE_ARTIFACT')
 return {'path':str(path),'sha256':sha(path),'bytes':s.st_size}
def check_artifact(row):
 require(artifact(row['path'])==row,'ARTIFACT_DRIFT')
def validate_artifacts(value):
 """Receipts alone are insufficient: validate every referenced original backup too."""
 count=0
 if isinstance(value,dict):
  if {'path','sha256','bytes'}<=set(value):check_artifact({k:value[k] for k in ('path','sha256','bytes')});count+=1
  for child in value.values():count+=validate_artifacts(child)
 elif isinstance(value,list):
  for child in value:count+=validate_artifacts(child)
 return count
@contextmanager
def private_log(path):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'ab',buffering=0) as f:yield f
def command(argv,log,*,env=None,stdout=None,timeout=180):
 # Never log an environment. Connection credentials only exist in the private child env.
 with private_log(log) as err:
  out=os.fdopen(os.open(stdout,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') if stdout else err
  try:
   result=subprocess.run([str(x) for x in argv],env=env,stdout=out,stderr=err,timeout=timeout)
   require(result.returncode==0,'SUBPROCESS_FAILED')
  finally:
   if stdout:out.close();Path(stdout).chmod(0o600)

def sqlite_counts(path):
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
  require(db.execute('pragma integrity_check').fetchone()==('ok',),'SQLITE_INTEGRITY_FAILED')
  violations=len(db.execute('pragma foreign_key_check').fetchall())
  names=[r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
  counts={n:db.execute('select count(*) from "'+n.replace('"','""')+'"').fetchone()[0] for n in names}
  return {'tables':counts,'application_id':db.execute('pragma application_id').fetchone()[0],'user_version':db.execute('pragma user_version').fetchone()[0],'foreign_key_violations':violations,'journal_mode':db.execute('pragma journal_mode').fetchone()[0]}

def seal_sqlite_copy(path):
 """Only the just-created destination is checkpointed; never the live source."""
 path=Path(path)
 with closing(sqlite3.connect(path)) as db:
  if db.execute('pragma journal_mode').fetchone()[0]=='wal':require(db.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()[0]==0,'BACKUP_CHECKPOINT_BUSY')
  require(db.execute('pragma journal_mode=DELETE').fetchone()[0]=='delete','BACKUP_SEAL_FAILED')
 require(not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')),'BACKUP_SIDECARS_REMAIN')

def sqlite_backup(source,directory,*,static_dispatch=False,strict_foreign_keys=False,timeout_seconds=60):
 source=Path(source);directory=private_dir(directory);receipt=directory/'receipt.json';prepared=directory/'prepared.json';target=directory/'snapshot.sqlite';partial=directory/'snapshot.partial'
 if receipt.exists():
  r=read_json(receipt);require(r['source']==str(source) and r['artifact']['path']==str(target),'SQLITE_RECEIPT_SOURCE_MISMATCH');check_artifact(r['artifact']);require(not any(Path(str(target)+s).exists() for s in ('-wal','-shm','-journal')),'SEALED_BACKUP_SIDECAR_DRIFT');return r
 if prepared.exists():
  r=read_json(prepared);present=target if target.exists() else partial;require(present.is_file() and sha(present)==r['artifact']['sha256'],'SQLITE_PREPARED_DRIFT')
  if present==partial:os.replace(partial,target)
  require(sqlite_counts(target)==r['metadata'],'SQLITE_PREPARED_METADATA_DRIFT');r['artifact']=artifact(target);atomic(receipt,r);return r
 require(not partial.exists() and not partial.is_symlink() and not target.exists() and not target.is_symlink(),'SQLITE_PARTIAL_REVIEW_REQUIRED')
 info=source.lstat();require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1,'SQLITE_SOURCE_ALIAS')
 started=utc();method='sqlite_online_backup_readonly_uri'
 deadline=time.monotonic()+timeout_seconds
 def progress(*_):require(time.monotonic()<=deadline,'SQLITE_BACKUP_DEADLINE')
 fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
 try:
  with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5)) as src,closing(sqlite3.connect(partial)) as dst:src.backup(dst,pages=256,sleep=.05,progress=progress)
 except sqlite3.OperationalError:
  # A known legacy dispatch DB is WAL-mode but has neither WAL nor SHM. Never clone a live WAL.
  require(static_dispatch and not any(Path(str(source)+s).exists() for s in ('-wal','-shm')),'SQLITE_ONLINE_BACKUP_FAILED_NO_SAFE_FALLBACK')
  signature=lambda: (source.stat().st_dev,source.stat().st_ino,source.stat().st_size,source.stat().st_mtime_ns)
  before=signature();first=sha(source);body=source.read_bytes();after=signature()
  require(before==after and first==hashlib.sha256(body).hexdigest()==sha(source) and not any(Path(str(source)+s).exists() for s in ('-wal','-shm')),'STATIC_DISPATCH_CHANGED')
  # Keep any failed attempt rather than overwrite it.
  if partial.exists():partial.rename(directory/'failed-online-attempt.sqlite')
  clone=directory/'verified-static-clone.sqlite';atomic(clone,body)
  fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
  with closing(sqlite3.connect(clone)) as src,closing(sqlite3.connect(partial)) as dst:src.backup(dst,pages=256,sleep=.05,progress=progress)
  method='stable_no_wal_no_shm_dispatch_clone_then_sqlite_backup'
 partial.chmod(0o600);seal_sqlite_copy(partial);metadata=sqlite_counts(partial)
 require(not strict_foreign_keys or metadata['foreign_key_violations']==0,'V2_SQLITE_FK_FAILED')
 row={'source':str(source),'source_device':info.st_dev,'source_inode':info.st_ino,'started_at':started,'completed_at':utc(),'method':method,'sealed_no_wal_shm':True,'metadata':metadata,'artifact':{**artifact(partial),'path':str(target)}}
 atomic(prepared,row);os.replace(partial,target);atomic(receipt,row);return row

def copy_private(source,target):
 source=Path(source);target=Path(target);require(not source.is_symlink(),'CONFIG_SYMLINK_REQUIRES_REVIEW')
 if not source.is_file():return {'source':str(source),'exists':False,'copied':False}
 info=source.stat();require(info.st_uid==os.getuid(),'CONFIG_SOURCE_OWNER')
 body=source.read_bytes();private_dir(target.parent)
 if target.exists():require(target.read_bytes()==body,'CONFIG_BACKUP_SOURCE_CHANGED')
 else:atomic(target,body)
 return {'source':str(source),'exists':True,'copied':True,'source_mode':oct(stat.S_IMODE(info.st_mode)),'artifact':artifact(target)}

def empty_pgpass(directory):
 path=Path(directory)/'empty.pgpass'
 if not path.exists():atomic(path,b'')
 info=path.lstat();require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_size==0,'EMPTY_PRIVATE_PGPASS_REQUIRED');return str(path)

def pg_env(params,*,readonly):
 require(bool(params.get('passfile')),'EXPLICIT_EMPTY_PGPASS_REQUIRED')
 result={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC','PGPASSFILE':str(params['passfile']),'PGCONNECT_TIMEOUT':'5','PGAPPNAME':'ikun_takeover_backup' if readonly else 'ikun_takeover_isolated_restore'}
 for key,name in [('host','PGHOST'),('port','PGPORT'),('dbname','PGDATABASE'),('user','PGUSER'),('password','PGPASSWORD')]:
  if key in params:result[name]=str(params[key])
 result['PGOPTIONS']='-c statement_timeout=120000 -c lock_timeout=3000'+(' -c default_transaction_read_only=on' if readonly else '')
 return result

def catalog_counts(connection):
 from psycopg import sql
 tables=connection.execute("select n.nspname,c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('r','p') and n.nspname not like 'pg_%' and n.nspname <> 'information_schema' order by 1,2").fetchall()
 return {schema+'.'+name:connection.execute(sql.SQL('select count(*) from {}').format(sql.Identifier(schema,name))).fetchone()[0] for schema,name in tables}

def postgres_dump(params,directory,pgbin):
 import psycopg
 directory=private_dir(directory);receipt=directory/'dump-receipt.json';prepared=directory/'dump-prepared.json';archive=directory/'database.dump';partial=directory/'database.partial';log=directory/'dump.error.log'
 if receipt.exists():
  r=read_json(receipt)
  for key in ('archive','counts_file','toc','decoded_sql'):check_artifact(r[key])
  return r
 if prepared.exists():
  r=read_json(prepared);present=archive if archive.exists() else partial;require(sha(present)==r['archive']['sha256'],'PG_PREPARED_DRIFT')
  if present==partial:os.replace(partial,archive)
  for key in ('counts_file','toc','decoded_sql'):check_artifact(r[key])
  atomic(receipt,r);return r
 require(not partial.exists() and not archive.exists(),'PG_PARTIAL_DUMP_REVIEW_REQUIRED')
 params={**params,'passfile':empty_pgpass(directory)}
 safe={k:str(params[k]) for k in ('host','port','dbname','user','password') if k in params};safe.update(connect_timeout='5',passfile=params['passfile'],options='-c default_transaction_read_only=on -c statement_timeout=120000 -c lock_timeout=3000')
 started=utc()
 with psycopg.connect(**safe,autocommit=True) as conn:
  with conn.transaction():
   conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
   require(conn.execute('SHOW transaction_read_only').fetchone()[0]=='on','PG_SOURCE_NOT_READONLY')
   snapshot=conn.execute('select pg_export_snapshot()').fetchone()[0]
   counts=catalog_counts(conn);count_file=directory/'table-counts.json';atomic(count_file,counts)
   command([pgbin/'pg_dump','--format=custom','--no-password','--lock-wait-timeout=3000','--snapshot='+snapshot,'--file='+str(partial)],log,env=pg_env(params,readonly=True),timeout=600)
 partial.chmod(0o600)
 toc=directory/'archive.toc';decoded=directory/'decoded.sql'
 command([pgbin/'pg_restore','--list',partial],log,stdout=toc)
 command([pgbin/'pg_restore','--exit-on-error','--file='+str(decoded),partial],log,timeout=300);decoded.chmod(0o600)
 row={'started_at':started,'completed_at':utc(),'consistent_snapshot':'exported repeatable-read snapshot shared by counts and pg_dump','table_count':len(counts),'archive':{**artifact(partial),'path':str(archive)},'counts_file':artifact(count_file),'toc':artifact(toc),'decoded_sql':artifact(decoded),'database_backup_scope':'one complete database, not cluster-global roles/tablespaces','restoration_acl_note':'original archive retains owners/ACL; drill skips them in isolated cluster'}
 atomic(prepared,row);os.replace(partial,archive);atomic(receipt,row);return row

def source_pg_params(config_path):
 from psycopg.conninfo import conninfo_to_dict
 config=read_json(config_path);paths=[Path(config[k]) for k in ('module_dsn_file','import_dsn_file')]
 values=[]
 for p in paths:
  require(p.is_file() and stat.S_IMODE(p.stat().st_mode)==0o600 and p.stat().st_uid==os.getuid(),'PRIVATE_DSN_REQUIRED')
  values.append(conninfo_to_dict(p.read_text().strip()))
 require(all(v.get('host')=='127.0.0.1' and v.get('port')=='55432' and bool(v.get('dbname')) for v in values),'ONLY_OWNED_LEGACY_PG_ENDPOINT')
 require(values[0]['dbname']==values[1]['dbname'],'DSN_DATABASE_MISMATCH')
 return {k:v for k,v in values[0].items() if k in ('host','port','dbname','user','password')}

def pinned_pg_params(spec,baseline):
 from psycopg.conninfo import conninfo_to_dict
 path=Path(spec['path']);info=path.lstat()
 require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and not any(p.is_symlink() for p in (path,*path.parents)),'PINNED_PG_SOURCE_IDENTITY')
 body=path.read_bytes();require(hashlib.sha256(body).hexdigest()==spec['sha256'],'PINNED_PG_SOURCE_HASH')
 values=[m[1] for line in body.decode('utf-8').splitlines() if (m:=re.fullmatch(r'\s*DATABASE_URL\s*=\s*(.*?)\s*',line))]
 require(len(values)==1,'PINNED_DATABASE_URL_EXACTLY_ONE');value=values[0]
 if value.startswith(('"',"'")):
  require(len(value)>=2 and value[-1]==value[0],'PINNED_DATABASE_URL_QUOTES');value=value[1:-1]
 require(value.startswith(('postgresql://','postgres://')) and not any(ord(c)<32 for c in value),'PINNED_DATABASE_URL_FORMAT')
 params=conninfo_to_dict(value)
 require(all(params.get(k)==baseline[k] for k in ('host','port','dbname')),'PINNED_DATABASE_URL_ENDPOINT_DATABASE_MISMATCH')
 require(params.get('user')==spec['user'] and bool(params.get('password')),'PINNED_DATABASE_URL_ROLE_OR_PASSWORD')
 return {k:v for k,v in params.items() if k in ('host','port','dbname','user','password')}

def select_source_role(params,log,*,backup_role_source):
 import psycopg
 params={**params,'passfile':empty_pgpass(Path(log).parent)}
 pinned={**pinned_pg_params(backup_role_source,params),'passfile':params['passfile']}
 candidates=[dict(params),pinned]
 for index,value in enumerate(candidates):
  try:
   safe={k:str(v) for k,v in value.items()};safe.update(connect_timeout='5',options='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=3000')
   with psycopg.connect(**safe,autocommit=True) as conn:
    with conn.transaction():
     conn.execute('SET TRANSACTION READ ONLY')
     enough,rls=conn.execute("select coalesce(bool_and(has_table_privilege(c.oid,'SELECT')),true),coalesce(bool_or(row_security_active(c.oid)),false) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('r','p') and n.nspname not like 'pg_%' and n.nspname <> 'information_schema'").fetchone()
     sequences=conn.execute("select coalesce(bool_and(has_sequence_privilege(c.oid,'SELECT')),true) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='S' and n.nspname not like 'pg_%' and n.nspname <> 'information_schema'").fetchone()[0]
     require(enough and not rls and sequences,'RESTRICTED_ROLE_INSUFFICIENT_FOR_FULL_BACKUP')
   return value,('configured_readonly_role' if index==0 else 'pinned_existing_web3_readonly_backup')
  except Exception as error:
   with private_log(log) as f:f.write((utc()+' '+type(error).__name__+'\n').encode())
 raise SafeFailure('PG_FULL_BACKUP_READONLY_ROLE_UNAVAILABLE')

def assert_drill_connection(params,data_directory):
 import psycopg
 host=Path(params['host']);require(str(host).startswith('/private/tmp/iktpg-') and host.is_dir() and not host.is_symlink() and stat.S_IMODE(host.stat().st_mode)==0o700,'DRILL_SOCKET_NOT_PRIVATE_TEMP')
 require(str(params['port'])!='55432','NEVER_RESTORE_TO_OLD_PORT')
 with psycopg.connect(**params,connect_timeout=5) as conn:
  actual=conn.execute('show data_directory').fetchone()[0]
 require(Path(actual).resolve()==Path(data_directory).resolve(),'DRILL_DATA_DIRECTORY_MISMATCH')

def postgres_restore(dump,directory,pgbin,*,protected_pids=()):
 import psycopg
 directory=private_dir(directory);receipt=directory/'restore-receipt.json'
 if receipt.exists():r=read_json(receipt);require(r['counts_match'],'RESTORE_RECEIPT_FAILED');return r
 data=directory/'pgdata';state=directory/'server-state.json';log=directory/'restore.error.log';pglog=directory/'postgres.log'
 require(not data.exists() and not state.exists(),'PARTIAL_RESTORE_REQUIRES_RECONCILIATION')
 socket=Path(tempfile.mkdtemp(prefix='iktpg-',dir='/private/tmp'));socket.chmod(0o700)
 command([pgbin/'initdb','-D',data,'-A','trust','--encoding=UTF8','--no-locale'],log,timeout=120)
 options=shlex.join(['-k',str(socket),'-p','65432','-c','listen_addresses=','-c','shared_buffers=32MB','-c','max_connections=8'])
 params={'host':str(socket),'port':'65432','dbname':'postgres','user':'lvlei','passfile':empty_pgpass(directory)};started=False;pid=None
 atomic(state,{'data_directory':str(data),'socket':str(socket),'pid':None,'stopped':False,'intent_at':utc()})
 try:
  command([pgbin/'pg_ctl','-D',data,'-l',pglog,'-o',options,'-w','start'],log,timeout=60);started=True
  pid=int((data/'postmaster.pid').read_text().splitlines()[0]);require(pid not in protected_pids,'DRILL_PID_IS_PROTECTED')
  atomic(state,{'pid':pid,'data_directory':str(data),'socket':str(socket),'started_at':utc(),'stopped':False})
  assert_drill_connection(params,data)
  # --clean applies ONLY after the independent socket/data_directory guard above.
  command([pgbin/'pg_restore','--dbname=postgres','--clean','--if-exists','--no-owner','--no-privileges','--exit-on-error','--single-transaction','--no-password',dump['archive']['path']],log,env=pg_env(params,readonly=False),timeout=600)
  with psycopg.connect(**params,options='-c default_transaction_read_only=on') as conn:counts=catalog_counts(conn)
  expected=read_json(dump['counts_file']['path']);require(counts==expected,'RESTORED_TABLE_COUNTS_MISMATCH')
  atomic(directory/'restored-table-counts.json',counts)
  row={'completed_at':utc(),'counts_match':True,'table_count':len(counts),'data_directory':str(data),'socket':str(socket),'source_archive_sha256':dump['archive']['sha256'],'owners_and_acls_skipped_for_drill_only':True,'old_database_writes':0,'restored_counts':artifact(directory/'restored-table-counts.json')}
 finally:
  lines=(data/'postmaster.pid').read_text().splitlines() if (data/'postmaster.pid').exists() else []
  if lines:
   actual_pid=int(lines[0]);require(len(lines)>=5 and (pid is None or actual_pid==pid) and Path(lines[1]).resolve()==data.resolve() and lines[3]=='65432' and Path(lines[4]).resolve()==socket.resolve() and actual_pid not in protected_pids,'DRILL_STOP_IDENTITY_FAILED')
   command([pgbin/'pg_ctl','-D',data,'-m','fast','-w','stop'],log,timeout=45)
  atomic(state,{'pid':pid,'data_directory':str(data),'socket':str(socket),'stopped':True,'stopped_at':utc()})
  try:socket.rmdir()
  except OSError:pass
 if 'row' not in locals():raise SafeFailure('RESTORE_FAILED')
 row['server_state']=artifact(state)
 atomic(receipt,row);return row
