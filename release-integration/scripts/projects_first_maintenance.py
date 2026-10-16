#!/usr/bin/env python3
"""Projects-only maintenance: existing owner CLI, existing website job, original DB inode."""
import argparse
import collections
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import subprocess
import time
import urllib.request
import uuid
from takeover_backup import SafeFailure,require,sha,atomic,private_dir,read_json,artifact,check_artifact,validate_artifacts,sqlite_backup,command,utc,private_log
from takeover_operator import ROOT,V2,CONTROL,JOURNAL,System,Journal,same_process,original_absent,guard,PLAN as LEGACY_PLAN

SOURCE='09afbcfd7ba7d809750d4b27c7599c952335b35f'
BASE='0ce180c33ea4be350ac57daa7dbfa5b5221e58cb'
LABEL='ca.ikun.v2.c0lite.web'
PLIST=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
PACKAGE=ROOT.parent/'projects/modules/projects/artifacts/formal-input-d0e25f64-79a3bb0b-v1/projects-input-v1.json'
PACKAGE_SHA='5afc6a274db8a1ec162a43660db8b5ee24a5058074afbd6f308bd32e302cec7e'
MANIFEST=CONTROL/'var/takeover-execution/final-inputs/source-manifest-v1.json'
MANIFEST_SHA='8f5a453a705dbe0ba4c3957c94098ba05684a95b1ef54ca16243fa90aa8fac1f'
DECISIONS=CONTROL/'var/takeover-execution/input-admissions-v1/projects-decisions-v1.json'
DECISIONS_SHA='79a3bb0b2d6177842c15ed0aa1461a1eb1c2056754085cd0d429409da0f98388'
REHEARSAL=ROOT/'release-integration/.runtime/v2-maintenance/projects-rehearsal-only/run-1792147026959'
REHEARSAL_SHA='5364810e3dcdc79790781cc7539dbfbe295facfaa98460cc5138cb4377f21ffd'
OUTPUT=ROOT/'release-integration/.runtime/v2-maintenance/projects-first/09af-5afc-v1'
PHASE='projects_first_09af_5afc_v1'
DATABASES={n:V2/'data'/n/(n+'.db') for n in ('auth','projects','hunter','tracking')}
ALLOWED_CHANGED_TABLES={'projects','project_sources','project_settings'}
IMPORTER='modules/projects/candidate/projects_service/takeover.py'
NEW_COUNTERS=('created_projects','new_mappings','new_identity_aliases','new_quarantine_records','new_field_quarantine_groups')
INITIAL_COUNTERS=dict(zip(NEW_COUNTERS,(32,32,1,1412,1444)))

def verify_apply(result,plan):
 require(result['package_sha256']==PACKAGE_SHA and result['snapshot_sha256']=='d0e25f6472aca37ff408ff4ff8219fb6953ab698e053add40dc14e7f44431d46' and result.get('dry_run') is None and result['importer_source_sha256']==plan['code_files'][IMPORTER],'OWNER_APPLY_RECEIPT_MISMATCH')
 expected={k:0 for k in NEW_COUNTERS} if result.get('replayed') is True else INITIAL_COUNTERS
 require(all(type(result[k]) is int and result[k]==v for k,v in expected.items()) and len(result['mappings'])==32,'OWNER_APPLY_COUNTS_MISMATCH')

def fingerprint(path):
 def atom(value):return [type(value).__name__,value.hex() if isinstance(value,bytes) else value]
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
  db.execute('PRAGMA query_only=ON')
  require(db.execute('PRAGMA integrity_check').fetchone()==('ok',) and not db.execute('PRAGMA foreign_key_check').fetchall(),'DATABASE_INTEGRITY_OR_FK_FAILED')
  tables={}
  for name, in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
   rows=collections.Counter(hashlib.sha256(json.dumps([atom(x) for x in row],ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest() for row in db.execute('SELECT * FROM "'+name.replace('"','""')+'"'))
   tables[name]={'rows':sum(rows.values()),'row_hash_counts':dict(rows)}
  return {'tables':tables,'application_id':db.execute('PRAGMA application_id').fetchone()[0],'user_version':db.execute('PRAGMA user_version').fetchone()[0]}
def preserved(before,after,*,auth=False):
 require(before['application_id']==after['application_id'] and before['user_version']==after['user_version']==2,'SCHEMA_CHANGED')
 require(set(before['tables'])==set(after['tables']),'TABLE_SET_CHANGED')
 for name,row in before['tables'].items():
  actual=after['tables'][name];require(not (collections.Counter(row['row_hash_counts'])-collections.Counter(actual['row_hash_counts'])),'ORIGINAL_ROWS_CHANGED')
  if auth or name not in ALLOWED_CHANGED_TABLES:require(row==actual,'NON_IMPORT_TABLE_CHANGED')

class WebOps(System):
 def __init__(self,log):super().__init__(log);self.socket_path=None
 def job(self):
  r=subprocess.run(['/bin/launchctl','print',self.domain+'/'+LABEL],capture_output=True,text=True,timeout=10)
  if r.returncode:require('Could not find service' in r.stdout+r.stderr,'WEB_JOB_QUERY_FAILED');return {'loaded':False,'pid':None}
  match=re.search(r'^\s*pid = (\d+)$',r.stdout,re.M);return {'loaded':True,'pid':int(match[1]) if match else None}
 def bootout(self):command(['/bin/launchctl','bootout',self.domain+'/'+LABEL],self.log,timeout=45)
 def bootstrap(self):command(['/bin/launchctl','bootstrap',self.domain,PLIST],self.log,timeout=45)
 def fence(self):
  require(not self.job()['loaded'],'WEBSITE_NOT_STOPPED')
  for name in ('auth','projects'):
   for path in (DATABASES[name],*(Path(str(DATABASES[name])+s) for s in ('-wal','-shm'))):
    if path.exists():require(not self.source_write_holders(path),'UNKNOWN_DATABASE_WRITER')
  result=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:4000','-sTCP:LISTEN','-Fp'],capture_output=True,text=True,timeout=10)
  require(result.returncode==1 and not result.stdout.strip() and not result.stderr.strip(),'WEBSITE_PORT_STILL_OPEN_OR_QUERY_FAILED')
  if self.socket_path and Path(self.socket_path).exists():
   result=subprocess.run(['/usr/sbin/lsof','-Fp','--',self.socket_path],capture_output=True,text=True,timeout=10)
   require(result.returncode==1 and not result.stdout.strip() and not result.stderr.strip(),'PROJECTS_SOCKET_STILL_OPEN_OR_QUERY_FAILED')
 def socket_proof(self,tree):
  pids={p['pid'] for p in tree};require(pids,'EMPTY_WEBSITE_TREE')
  r=subprocess.run(['/usr/sbin/lsof','-U','-a','-p',','.join(map(str,sorted(pids))),'-Fpn'],capture_output=True,text=True,timeout=10)
  require(r.returncode==0,'WEB_IPC_HANDLE_QUERY_FAILED');sockets={};pid=None
  for line in r.stdout.splitlines():
   if line.startswith('p'):pid=int(line[1:])
   elif line.startswith('n/private/tmp/ikp-') and line.endswith('/p.sock'):sockets.setdefault(line[1:],set()).add(pid)
  require(len(sockets)==1,'UNIQUE_MANAGED_PROJECTS_IPC_REQUIRED');path,holders=next(iter(sockets.items()));p=Path(path);s=p.lstat()
  require(p.parent.parent==Path('/private/tmp') and not p.parent.is_symlink() and stat.S_IMODE(p.parent.stat().st_mode)==0o700 and stat.S_ISSOCK(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and holders<=pids,'PROJECTS_IPC_NOT_OWNED')
  return {'path':path,'holder_pids':sorted(holders),'mode':'0600'}
 def ready(self,timeout=30):
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   try:
    with opener.open('http://127.0.0.1:4000/health/ready',timeout=2) as r:
     data=json.load(r)['data']
     if r.status==200 and data.get('service')=='website' and data.get('profile')=='c0-lite' and data.get('status')=='ready':return
   except Exception:pass
   time.sleep(.2)
  raise SafeFailure('WEBSITE_NOT_READY')

def stop_web_once(state,save,ops,expected,protected_pids,*,timeout=60,expected_tree=None):
 if state.get('stopped'):
  require(not ops.job()['loaded'] and all(original_absent(ops,p) for p in state['tree']),'STOPPED_WEB_REAPPEARED');return
 if state.get('stop_intent'):require(not ops.job()['loaded'],'WEB_STOP_UNKNOWN_NO_AUTOMATIC_RETRY')
 else:
  job=ops.job();current=ops.process(expected['pid']);require(job['loaded'] and job['pid']==expected['pid'] and same_process(current,expected) and current['cwd']==expected['cwd'],'WEB_IDENTITY_DRIFT')
  for p in expected_tree or []:require(same_process(ops.process(p['pid']),p),'REVIEWED_WEB_CHILD_IDENTITY_DRIFT')
  tree=ops.tree(expected['pid']);require(not {p['pid'] for p in tree}&set(protected_pids),'PROTECTED_PROCESS_IN_WEB_TREE')
  state.update(stop_intent=utc(),tree=tree);save()
  require(same_process(ops.process(expected['pid']),expected),'WEB_IDENTITY_DRIFT_BEFORE_BOOTOUT')
  tree=ops.tree(expected['pid']);require(not {p['pid'] for p in tree}&set(protected_pids),'PROTECTED_PROCESS_IN_WEB_TREE')
  state['tree']=list({(p['pid'],p['started_utc']):p for p in [*state['tree'],*tree]}.values());save();ops.bootout()
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if not ops.job()['loaded'] and all(original_absent(ops,p) for p in state['tree']):break
  time.sleep(.1)
 else:raise SafeFailure('WEB_TREE_NOT_EXITED_NO_FORCE_KILL')
 ops.fence();state['stopped']=True;save()
def restore_web_once(state,save,ops,*,timeout=30):
 if not ops.job()['loaded']:
  require(not state.get('restore_intent'),'WEB_BOOTSTRAP_UNKNOWN_NO_AUTOMATIC_RETRY');ops.fence();state['restore_intent']=utc();save();ops.bootstrap()
 ops.ready(timeout);job=ops.job();current=ops.process(job['pid']) if job['pid'] else None
 require(current is not None and current['cwd']==str(V2/'releases'/BASE),'RESTORED_WEB_IDENTITY_MISMATCH')
 tree=ops.tree(job['pid']);socket=ops.socket_proof(tree);state.update(restored=True,restored_at=utc(),new_process=current,new_tree=tree,new_socket=socket);save()

def immutable_inputs(plan):
 require(plan['phase']==PHASE and plan['package']==str(PACKAGE) and plan['package_sha256']==PACKAGE_SHA and plan['source_commit']==SOURCE and plan['code_root']==str(OUTPUT/'owner-code'),'PLAN_SCOPE_MISMATCH')
 for path,expected in ((PACKAGE,PACKAGE_SHA),(MANIFEST,MANIFEST_SHA),(DECISIONS,DECISIONS_SHA),(REHEARSAL/'REHEARSAL_ONLY.json',REHEARSAL_SHA)):
  info=path.lstat();require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and sha(path)==expected,'APPROVED_INPUT_DRIFT')
 validate_artifacts(read_json(REHEARSAL/'REHEARSAL_ONLY.json'))
 manifest=read_json(MANIFEST);validate_artifacts(manifest);validate_artifacts(read_json(manifest['operator_receipt']['path']))
 for relative,expected in plan['code_files'].items():
  p=Path(plan['code_root'])/relative;s=p.lstat();require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and not any(x.is_symlink() for x in p.parents) and sha(p)==expected,'OWNER_CODE_DRIFT')
 for relative,expected in plan['helper_files'].items():require(sha(ROOT/relative)==expected,'REVIEWED_HELPER_DRIFT')
 require(sha(plan['python'])==plan['python_sha256'] and sha(LEGACY_PLAN)==plan['sealed_protection_plan_sha256'],'INTERPRETER_OR_PROTECTION_PLAN_DRIFT')
 require(sha(PLIST)==plan['web_plist_sha256'] and sha(V2/'config/web.environment.json')==plan['web_environment_sha256'] and read_json(V2/'owner.json')['candidate_sha']==BASE,'WEBSITE_CONFIG_OR_RELEASE_DRIFT')
 binding=V2/'releases'/BASE/'release-integration/c0-lite/evidence/build-binding.json';require(sha(binding)==plan['website_binding_sha256'],'WEBSITE_BINDING_CHANGED')
 for group in ('sources','compiled'):
  for relative,expected in read_json(binding)[group].items():require(sha(V2/'releases'/BASE/relative)==expected,'WEBSITE_SOURCE_OR_BUILD_DRIFT')
def peer_guard(ops,plan):
 sealed=read_json(LEGACY_PLAN);sealed['protected_processes']={k:v for k,v in sealed['protected_processes'].items() if k!='v2_web'}
 proof=guard(ops,sealed);proof['worker_health']=worker_health();return proof
def worker_health():
 result={};opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for name,port,flag in (('hunter',4011,'external_io_enabled'),('tracking',4012,'external_collection_enabled')):
  with opener.open('http://127.0.0.1:'+str(port)+'/health/ready',timeout=3) as response:
   require(response.status==200 and json.load(response)['data'].get(flag) is False,'WORKER_NOT_READY_OR_EXTERNAL_IO_CHANGED');result[name]={'status':200,flag:False}
 return result
def prepare(path):
 require(Path(path).parent==OUTPUT and Path(path).suffix=='.json' and not any(p.is_symlink() for p in Path(path).parents),'PRIVATE_PHASE_PLAN_PATH_REQUIRED')
 private_dir(OUTPUT);code=private_dir(OUTPUT/'owner-code');names=subprocess.check_output(['git','ls-tree','-r','--name-only',SOURCE,'--','modules/projects/candidate','schemas/projects'],cwd=ROOT,text=True).splitlines();files={}
 for relative in names:
  require('..' not in Path(relative).parts and not Path(relative).is_absolute(),'UNSAFE_OWNER_CODE_PATH');body=subprocess.check_output(['git','show',SOURCE+':'+relative],cwd=ROOT);dest=code/relative;private_dir(dest.parent)
  if dest.exists():require(sha(dest)==hashlib.sha256(body).hexdigest(),'STAGED_OWNER_CODE_DRIFT')
  else:atomic(dest,body)
  files[relative]=hashlib.sha256(body).hexdigest()
 env=read_json(V2/'config/web.environment.json');ops=WebOps(OUTPUT/'commands.private.log');job=ops.job();require(job['loaded'] and job['pid'],'WEB_NOT_RUNNING_FOR_NEW_PLAN');process=ops.process(job['pid']);require(process and process['cwd']==str(V2/'releases'/BASE),'WEB_BASELINE_MISMATCH')
 tree=ops.tree(job['pid']);socket=ops.socket_proof(tree)
 plan={'phase':PHASE,'source_commit':SOURCE,'package':str(PACKAGE),'package_sha256':PACKAGE_SHA,'manifest_sha256':MANIFEST_SHA,'decisions_sha256':DECISIONS_SHA,'code_root':str(code),'code_files':files,'helper_files':{p:sha(ROOT/p) for p in ('release-integration/scripts/takeover_backup.py','release-integration/scripts/takeover_operator.py')},'python':env['PROJECTS_PYTHON'],'python_sha256':sha(env['PROJECTS_PYTHON']),'initial_web':process,'initial_tree':tree,'initial_socket':socket,'sealed_protection_plan_sha256':sha(LEGACY_PLAN),'web_plist_sha256':sha(PLIST),'web_environment_sha256':sha(V2/'config/web.environment.json'),'website_binding_sha256':sha(V2/'releases'/BASE/'release-integration/c0-lite/evidence/build-binding.json'),'tool_source_sha256':sha(__file__),'source_rehearsal_sha256':REHEARSAL_SHA,'prepared_at':utc(),'auth_no_import':True,'workers_stop':False,'next_build_required':False}
 immutable_inputs(plan);ops.ready(3);plan['protected_before']=peer_guard(ops,plan);require(not Path(path).exists(),'NEW_PLAN_PATH_REQUIRED');atomic(path,plan);print(json.dumps({'state':'PREPARED_PROJECTS_ONLY_NOT_EXECUTED','plan':str(path),'sha256':sha(path),'staged_code_files':len(files)}))

def readonly_status(path,expected_sha):
 require(sha(path)==expected_sha,'EXECUTION_PLAN_HASH_MISMATCH');plan=read_json(path);require(plan['tool_source_sha256']==sha(__file__),'REVIEWED_TOOL_CHANGED');immutable_inputs(plan)
 before=sha(JOURNAL);data=read_json(JOURNAL);probe=Journal();probe.data=data;probe.validate()
 state=data.get('maintenance_steps',{}).get(PHASE,{});window=(state.get('windows') or [{}])[-1];ops=WebOps(None);ops.socket_path=plan['initial_socket']['path'];protected=peer_guard(ops,plan);job=ops.job()
 alive=[p['pid'] for p in window.get('tree',[]) if not original_absent(ops,p)];fence='not_checked_while_loaded'
 if not job['loaded']:
  try:ops.fence();fence='clear'
  except SafeFailure as error:fence=str(error)
 require(sha(JOURNAL)==before,'JOURNAL_CHANGED_DURING_READONLY_QUERY')
 result={'state':state.get('state','not_started'),'website_loaded':job['loaded'],'website_pid':job['pid'],'stop_intent':bool(window.get('stop_intent')),'recorded_stopped':bool(window.get('stopped')),'original_tree_still_alive':alive,'writer_port_socket_fence':fence,'can_reconcile_stop_on_approved_execute':bool(window.get('stop_intent')) and not job['loaded'] and not alive and fence=='clear','restore_intent':bool(window.get('restore_intent')),'restored':bool(window.get('restored')),'import_intent':bool(state.get('import_intent')),'protected':protected,'actions':0,'database_connections':0,'journal_written':False}
 print(json.dumps(result));return result

def execute(candidate,path,expected_sha,*,resume_recovered=False):
 info=Path(path).lstat();require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and not any(p.is_symlink() for p in Path(path).parents),'PRIVATE_PHASE_PLAN_REQUIRED')
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==candidate and subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/integration' and not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'EXACT_CLEAN_INTEGRATION_REQUIRED')
 require(subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip()=='63e8a2857241c6a76226f21435e40db9736a1e7e','MAIN_CHANGED');require(sha(path)==expected_sha,'EXECUTION_PLAN_HASH_MISMATCH');plan=read_json(path);require(plan['tool_source_sha256']==sha(__file__),'REVIEWED_TOOL_CHANGED');immutable_inputs(plan)
 private_dir(OUTPUT);ops=WebOps(OUTPUT/'commands.private.log');ops.socket_path=plan['initial_socket']['path']
 with Journal() as journal:
  phases=journal.data.setdefault('maintenance_steps',{});state=phases.setdefault(PHASE,{'package_sha256':PACKAGE_SHA,'manifest_sha256':MANIFEST_SHA,'steps':{},'windows':[]})
  require(state['package_sha256']==PACKAGE_SHA and state['manifest_sha256']==MANIFEST_SHA,'MAINTENANCE_INPUT_BINDING_CHANGED')
  def save():journal.data['maintenance_state']=state.get('state','projects_maintenance_in_progress');journal.save()
  if state.get('state')=='complete':validate_artifacts(state['result']);validate_artifacts(read_json(state['result']['path']));print(json.dumps({'state':'ALREADY_COMPLETE_NO_ACTION','receipt':state['result']['path']}));return
  if state['windows'] and state['windows'][-1].get('restored'):
   require(resume_recovered,'RECOVERED_WINDOW_REQUIRES_NEW_REVIEWED_PLAN');require(same_process(ops.process(plan['initial_web']['pid']),plan['initial_web']),'NEW_REVIEWED_WEB_BASELINE_REQUIRED')
  if not state['windows'] or state['windows'][-1].get('restored'):state['windows'].append({})
  window=state['windows'][-1];save()
  def step(name,fn):
   previous=state['steps'].get(name)
   if previous and previous.get('state')=='done':check_artifact(previous['receipt']);value=read_json(previous['receipt']['path']);validate_artifacts(value);return value
   directory=private_dir(previous['directory'] if previous else OUTPUT/(name+'-'+uuid.uuid4().hex));state['steps'][name]={'state':'intent','directory':str(directory)};save();value=fn(directory);validate_artifacts(value);out=directory/'receipt.json';atomic(out,value);state['steps'][name]={'state':'done','directory':str(directory),'receipt':artifact(out)};save();return value
  def backups(directory):
   return {name:sqlite_backup(db,private_dir(directory/name),strict_foreign_keys=True) for name,db in DATABASES.items()}
  def owner(receipt,*,apply=False):
   ops.fence();argv=[plan['python'],'-m','projects_service.takeover','--database',str(DATABASES['projects']),'--package',str(PACKAGE),'--expected-package-sha256',PACKAGE_SHA,'--receipt',str(receipt)]
   if apply:argv+=['--mapping',str(OUTPUT/'projects-export.json'),'--apply','--writer-stopped']
   command(argv,OUTPUT/'owner-cli.private.log',env={'PATH':'/usr/bin:/bin:/opt/homebrew/bin','LANG':'C.UTF-8','TZ':'UTC','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PYTHONSAFEPATH':'1','PYTHONPATH':str(Path(plan['code_root'])/'modules/projects/candidate')},stdout=OUTPUT/('cli-stdout-'+uuid.uuid4().hex+'.json'),timeout=60)
   return read_json(receipt)
  try:
   peer_guard(ops,plan);before=step('before_online_'+str(len(state['windows'])),backups);validate_artifacts(before)
   stop_web_once(window,save,ops,plan['initial_web'],[v['pid'] for k,v in read_json(LEGACY_PLAN)['protected_processes'].items() if k!='v2_web'],expected_tree=plan['initial_tree']);peer_guard(ops,plan)
   stopped=step('stopped_window_'+str(len(state['windows'])),backups);auth_before=fingerprint(stopped['auth']['artifact']['path']);projects_before=fingerprint(stopped['projects']['artifact']['path'])
   require(auth_before['application_id']==1229652484 and projects_before['application_id']==1229652483 and auth_before['user_version']==projects_before['user_version']==2,'STOPPED_STORE_IDENTITY_MISMATCH')
   query=owner(OUTPUT/('prequery-'+uuid.uuid4().hex+'.json'));require(query.get('dry_run') is True,'PREQUERY_NOT_READONLY')
   if not state.get('import_intent'):
    require(not (OUTPUT/'projects-apply-receipt.json').exists() and not (OUTPUT/'projects-export.json').exists(),'UNEXPECTED_FORMAL_EXPORT_EXISTS')
    require(projects_before['tables']==read_json(REHEARSAL/'before.private.json')['tables'] and query.get('replayed') is False,'CURRENT_PROJECTS_BASELINE_CHANGED_REHEARSAL_REQUIRED')
    require(all(query[k]==v for k,v in INITIAL_COUNTERS.items()),'CURRENT_DRYRUN_DIFFERS_FROM_REHEARSAL')
   else:preserved({'tables':read_json(REHEARSAL/'before.private.json')['tables'],'application_id':1229652483,'user_version':2},projects_before)
   state['import_intent']=state.get('import_intent') or utc();window['apply_intent']=utc();save();result=owner(OUTPUT/'projects-apply-receipt.json',apply=True)
   verify_apply(result,plan)
   state['apply_returned']=utc();save();ops.fence();after=step('after_import_'+str(len(state['windows'])),backups)
   preserved(auth_before,fingerprint(after['auth']['artifact']['path']),auth=True);preserved(projects_before,fingerprint(after['projects']['artifact']['path']))
   query=owner(OUTPUT/('postquery-'+uuid.uuid4().hex+'.json'));require(query.get('dry_run') is True and query.get('replayed') is True and all(query[k]==0 for k in NEW_COUNTERS),'OWNER_RECONCILE_NOT_ZERO')
   mapping=read_json(OUTPUT/'projects-export.json');require(all(mapping[k]==result[k] for k in ('contract','execution_id','package_sha256','snapshot_sha256','mappings')),'PERSISTED_EXPORT_MISMATCH')
   peer_guard(ops,plan);restore_web_once(window,save,ops);immutable_inputs(plan);protected=peer_guard(ops,plan)
   receipt={'state':'PASS_PROJECTS_FIRST_RUNTIME_IMPORT','candidate':candidate,'completed_at':utc(),'source_commit':SOURCE,'package_sha256':PACKAGE_SHA,'source_manifest_sha256':MANIFEST_SHA,'owner_receipt':artifact(OUTPUT/'projects-apply-receipt.json'),'projects_export':artifact(OUTPUT/'projects-export.json'),'mapping_rows':len(mapping['mappings']),'before_online':before,'stopped':stopped,'after_import':after,'auth_all_rows_unchanged':True,'existing_projects_rows_preserved':True,'non_import_tables_unchanged':True,'owner_readonly_reconcile_zero_new':True,'web_window':window,'protected_after':protected,'workers_stopped':False,'schema_version':2,'new_provider_calls':0,'new_wss_connections':0,'Watch_writes':0,'next_builds':0,'website_code_unchanged':BASE}
   target=OUTPUT/'final-receipt.json';atomic(target,receipt);state.update(state='complete',result=artifact(target));journal.data['migrated_domains']=list(dict.fromkeys([*journal.data.get('migrated_domains',[]),'projects']));save();print(json.dumps({'state':receipt['state'],'receipt':str(target),'sha256':sha(target),'mapping_rows':len(mapping['mappings'])}))
  except BaseException as error:
   recovery='not_needed'
   try:
    if window.get('stopped') and not window.get('restored'):
     immutable_inputs(plan);peer_guard(ops,plan);ops.fence();pf=fingerprint(DATABASES['projects']);af=fingerprint(DATABASES['auth']);require(pf['user_version']==af['user_version']==2 and pf['application_id']==1229652483 and af['application_id']==1229652484,'RECOVERY_SCHEMA_NOT_COMPATIBLE')
     if window.get('apply_intent'):preserved(auth_before,af,auth=True);preserved(projects_before,pf)
     restore_web_once(window,save,ops);recovery='website_restored_without_database_rollback'
   except BaseException:recovery='blocked_unknown_writer_or_restore_state'
   state.update(state='partial_or_failed',last_failure={'at':utc(),'reason':str(error) if isinstance(error,SafeFailure) else type(error).__name__,'recovery':recovery,'package_unchanged':True});save();atomic(OUTPUT/('failure-'+uuid.uuid4().hex+'.json'),state['last_failure']);print(json.dumps({'state':'PROJECTS_MAINTENANCE_PARTIAL_OR_FAILED',**state['last_failure']}));raise SystemExit(1)

def main():
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--prepare',action='store_true');group.add_argument('--status',action='store_true');group.add_argument('--execute',action='store_true');parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256');parser.add_argument('--candidate');parser.add_argument('--resume-recovered',action='store_true');args=parser.parse_args()
 if args.prepare:prepare(Path(args.plan));return
 if args.status:require(args.plan_sha256,'REVIEWED_PLAN_HASH_REQUIRED');readonly_status(Path(args.plan),args.plan_sha256);return
 require(args.plan_sha256 and args.candidate,'REVIEWED_PLAN_AND_CANDIDATE_REQUIRED')
 def interrupt(*_):raise SafeFailure('OPERATOR_INTERRUPTED')
 signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt);execute(args.candidate,Path(args.plan),args.plan_sha256,resume_recovered=args.resume_recovered)

if __name__=='__main__':main()
