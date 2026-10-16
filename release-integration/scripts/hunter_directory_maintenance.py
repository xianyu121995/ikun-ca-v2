#!/usr/bin/env python3
"""Single Hunter maintenance phase. Original owner migrator/importer and launch wrapper."""
import argparse
import collections
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import sqlite3
import stat
import subprocess
import time
import urllib.request
import uuid

from takeover_backup import SafeFailure,require,sha,private_dir,atomic,artifact,read_json,validate_artifacts,sqlite_backup,copy_private,command,utc
from takeover_operator import ROOT,V2,JOURNAL,Journal,System,guard,same_process,original_absent,PLAN as LEGACY_PLAN
from projects_first_maintenance import fingerprint,stop_web_once as stop_owned_job_once,WebOps
from prepare_hunter_directory_maintenance import SOURCE,PACKAGE,PACKAGE_SHA,PROJECTS,PROJECTS_SHA,INTAKE,INTAKE_SHA,REHEARSAL,REHEARSAL_SHA
import night_worker_ops as night

PREPARATION=ROOT/'release-integration/.runtime/v2-maintenance/hunter-f9-preparation-v1/PREPARATION-ONLY.json'
PREPARATION_SHA='1d33301b42c993d6091914d08e7a436daae7a97ff8a407f8c0c96b6fa1226b37'
OUTPUT=ROOT/'release-integration/.runtime/v2-maintenance/hunter-first/f9-90b-v1'
LABEL='ca.ikun.v2.c0lite.hunter'
PLIST=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
DATABASE=V2/'data/hunter/hunter.db'
PHASE='hunter_directory_f9_90b_v1'
OLD_RELEASE='75b81a2b5210e41bdf8522467c7fba2a6a6e693c'
RELEASE=V2/'releases'/SOURCE
PLAN_DIR=V2/'plans/hunter'/SOURCE
ACCEPTANCE=V2/'config'/('hunter.accepted.'+SOURCE+'.json')
DATABASES={n:V2/'data'/n/(n+'.db') for n in ('auth','projects','hunter','tracking')}
PREFIX='legacy_takeover_v2:'


def private_file(path):
 path=Path(path);s=path.lstat()
 require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and not any(p.is_symlink() for p in path.parents),'PRIVATE_FILE_REQUIRED')
 return path


def reader_files(intake):
 return {p:h for p,h in intake['staged_git_sha256'].items() if p.startswith('services/hunter-worker/python/hunterradar/') or p=='services/hunter-worker/python/requirements-lock.txt' or p.startswith('schemas/hunter/') and p.endswith('.sql')}


def stable_state(path):
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
  db.execute('PRAGMA query_only=ON')
  return {key:hashlib.sha256(value.encode()).hexdigest() for key,value in db.execute('SELECT key,value FROM state') if key!='retention_clock_highwater'}


def preserve_hunter(before_path,after_path):
 before=fingerprint(before_path);after=fingerprint(after_path)
 require(before['application_id']==after['application_id']==0x494B0201 and before['user_version'] in (4,5) and after['user_version']==5,'HUNTER_SCHEMA_IDENTITY_MISMATCH')
 for name,row in before['tables'].items():
  if name=='state':continue
  actual=after['tables'].get(name);require(actual is not None and not (collections.Counter(row['row_hash_counts'])-collections.Counter(actual['row_hash_counts'])),'ORIGINAL_HUNTER_ROWS_CHANGED')
  if name not in ('hunters','_schema_migrations','_migration_checksums','hunter_takeover_runs','hunter_takeover_rows','hunter_takeover_baselines','hunter_takeover_conflicts','hunter_takeover_seen_times','hunter_takeover_project_refs'):require(row==actual,'NON_IMPORT_HUNTER_TABLE_CHANGED')
 old=stable_state(before_path);new=stable_state(after_path)
 require(all(new.get(key)==value for key,value in old.items()),'ORIGINAL_HUNTER_STATE_CHANGED')
 require(all(key in old or key.startswith(PREFIX) for key in new),'UNEXPECTED_HUNTER_STATE_KEY')


def expected_job():
 return {'Label':LABEL,'ProgramArguments':[str(V2/'venv/bin/python'),'-I',str(PLAN_DIR/'night_worker_ops.py'),'run','--plan',str(PLAN_DIR/'worker.json')],'WorkingDirectory':str(V2/'jobs/hunter'),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'ExitTimeOut':30,'Umask':0o077,'Nice':5,'ProcessType':'Background','StandardOutPath':str(V2/'logs/hunter.log'),'StandardErrorPath':str(V2/'logs/hunter.error.log')}


class HunterOps(System):
 def job(self):
  r=subprocess.run(['/bin/launchctl','print',self.domain+'/'+LABEL],capture_output=True,text=True,timeout=10)
  if r.returncode:require('Could not find service' in r.stdout+r.stderr,'HUNTER_JOB_QUERY_FAILED');return {'loaded':False,'pid':None}
  m=re.search(r'^\s*pid = (\d+)$',r.stdout,re.M);return {'loaded':True,'pid':int(m[1]) if m else None}
 def bootout(self):command(['/bin/launchctl','bootout',self.domain+'/'+LABEL],self.log,timeout=45)
 def bootstrap(self):command(['/bin/launchctl','bootstrap',self.domain,PLIST],self.log,timeout=45)
 def fence(self):
  require(not self.job()['loaded'],'HUNTER_NOT_STOPPED')
  for path in (DATABASE,Path(str(DATABASE)+'-wal'),Path(str(DATABASE)+'-shm')):
   if path.exists():require(not self.source_write_holders(path),'UNKNOWN_HUNTER_WRITER')
  r=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:4011','-sTCP:LISTEN','-Fp'],capture_output=True,text=True,timeout=10)
  require(r.returncode==1 and not r.stdout.strip() and not r.stderr.strip(),'HUNTER_PORT_OPEN_OR_QUERY_FAILED')
 def ready(self,timeout=30):
  deadline=time.monotonic()+timeout;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  while time.monotonic()<deadline:
   try:
    with opener.open('http://127.0.0.1:4011/health/ready',timeout=2) as r:
     data=json.load(r)['data']
     if r.status==200 and data.get('service')=='hunter' and data.get('external_io_enabled') is False:return
   except Exception:pass
   time.sleep(.2)
  raise SafeFailure('HUNTER_NOT_READY_HARDOFF')


def peers(ops,plan):
 proof=guard(ops,plan['during_protection'])
 for process in plan['web_tree']:require(same_process(ops.process(process['pid']),process),'PROTECTED_WEB_CHILD_CHANGED')
 require(WebOps(None).socket_proof(ops.tree(plan['web_tree'][0]['pid']))==plan['web_socket'],'PROTECTED_WEB_SOCKET_CHANGED')
 binding=read_json(plan['web_binding']['path']);require(sha(plan['web_binding']['path'])==plan['web_binding']['sha256'],'PROTECTED_WEB_BINDING_CHANGED')
 for group in ('sources','compiled'):
  for path,h in binding[group].items():require(sha(V2/'releases'/plan['web_release']/path)==h,'PROTECTED_WEB_BUILD_CHANGED')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for name,port in (('website',4000),('tracking',4012)):
  with opener.open('http://127.0.0.1:'+str(port)+'/health/ready',timeout=3) as r:
   data=json.load(r)['data'];require(r.status==200 and data.get('service')==name,'PROTECTED_SERVICE_NOT_READY')
   if name=='tracking':require(data.get('external_collection_enabled') is False,'TRACKING_EXTERNAL_IO_CHANGED')
 return proof


def immutable(plan):
 require(plan['phase']==PHASE and plan['source_commit']==SOURCE and plan['package_sha256']==PACKAGE_SHA and plan['runtime_release']==str(RELEASE),'HUNTER_PLAN_SCOPE_MISMATCH')
 for path,h in ((PROJECTS,PROJECTS_SHA),(INTAKE,INTAKE_SHA),(REHEARSAL,REHEARSAL_SHA),(PACKAGE,PACKAGE_SHA),(PREPARATION,PREPARATION_SHA)):
  require(sha(private_file(path))==h,'APPROVED_HUNTER_INPUT_DRIFT')
 validate_artifacts(read_json(PROJECTS));validate_artifacts(read_json(REHEARSAL))
 for path,h in plan['helper_files'].items():require(sha(ROOT/path)==h,'REVIEWED_HUNTER_HELPER_DRIFT')
 validate_artifacts(read_json(PREPARATION));validate_artifacts(plan['acceptance']);validate_artifacts(plan['reader_plan_file'])
 require(plan['runtime_files']==reader_files(read_json(INTAKE)) and plan['code_root']==read_json(INTAKE)['staged_code_root'],'RUNTIME_SELECTION_DRIFT')
 require(sha(LEGACY_PLAN)==plan['legacy_plan_sha256'] and sha(private_file(V2/'config/hunter.environment.json'))==plan['hunter_environment_sha256'] and sha(private_file(V2/'config/web.environment.json'))==plan['web_environment_sha256'],'ORIGINAL_SERVICE_CONFIG_DRIFT')
 require(sha(plan['python'])==plan['python_sha256'] and sha(V2/'venv/bin/python')==plan['launcher_python_sha256'],'HUNTER_INTERPRETER_DRIFT')
 for path,h in plan['runtime_files'].items():require(sha(private_file(Path(plan['code_root'])/path))==h,'STAGED_F9_RUNTIME_DRIFT')
 require(plan['reader_plan']['runtime_sha256']==plan['runtime_files'] and plan['reader_plan']['source_commit']==SOURCE,'READER_PLAN_SOURCE_MISMATCH')
 base=copy.deepcopy(read_json(read_json(PREPARATION)['future_plan']['path']));base['runtime_sha256']=plan['runtime_files'];base['acceptance_sha256']=plan['acceptance']['sha256'];base['previous_worker_release']=None;require(base==plan['reader_plan'],'READER_PLAN_FIELDS_DRIFT')


def prepare(path):
 require(Path(path).parent==OUTPUT and not os.path.lexists(path) and not any(p.is_symlink() for p in Path(path).parents),'NEW_HUNTER_PLAN_REQUIRED');private_dir(OUTPUT)
 require(sha(PREPARATION)==PREPARATION_SHA,'READER_PREPARATION_DRIFT');p=read_json(PREPARATION);intake=read_json(INTAKE);files=reader_files(intake)
 require(files and all('/tests/' not in path and '/docs/' not in path and Path(path).name not in ('.env','.env.local') for path in files),'UNEXPECTED_RUNTIME_SELECTION')
 ops=HunterOps(None);job=ops.job();require(job['loaded'] and job['pid'],'CURRENT_HUNTER_NOT_RUNNING');current=ops.process(job['pid']);require(current and current['cwd']==str(V2/'jobs/hunter'),'CURRENT_HUNTER_CWD_CHANGED')
 cfg=plistlib.loads(private_file(PLIST).read_bytes());reader='f9' if cfg==expected_job() else 'legacy4'
 if reader=='legacy4':
  expected=[str(V2/'venv/bin/python'),'-I',str(V2/'plans/hunter'/OLD_RELEASE/'night_worker_ops.py'),'run','--plan',str(V2/'plans/hunter'/OLD_RELEASE/'worker.json')]
  require(cfg.get('Label')==LABEL and cfg.get('ProgramArguments')==expected,'UNAPPROVED_CURRENT_HUNTER_LAUNCHER')
  require(sha(PLIST)==read_json(LEGACY_PLAN)['protected_files_sha256'][str(PLIST)],'LEGACY_HUNTER_PLIST_DRIFT')
 new=copy.deepcopy(read_json(p['future_plan']['path']));frozen=copy.deepcopy(read_json(p['future_acceptance']['path']));new['runtime_sha256']=frozen['runtime_sha256']=files;new['previous_worker_release']=None
 acceptance_copy=OUTPUT/(Path(path).stem+'.acceptance.json');reader_copy=OUTPUT/(Path(path).stem+'.worker-plan.json');require(not os.path.lexists(acceptance_copy) and not os.path.lexists(reader_copy),'NEW_PLAN_ARTIFACT_NAMES_REQUIRED')
 frozen_bytes=(json.dumps(frozen,indent=2)+'\n').encode();new['acceptance_sha256']=hashlib.sha256(frozen_bytes).hexdigest();atomic(acceptance_copy,frozen_bytes);atomic(reader_copy,new)
 projection=read_json(p['during_hunter_protection']['path']);projects=read_json(PROJECTS);web=projects['website_code_unchanged'];binding=V2/'releases'/web/'release-integration/c0-lite/evidence/build-binding.json'
 plan={'phase':PHASE,'source_commit':SOURCE,'package_sha256':PACKAGE_SHA,'runtime_release':str(RELEASE),'code_root':p['source_code_root'],'runtime_files':files,'reader_plan':new,'acceptance':artifact(acceptance_copy),'reader_plan_file':artifact(reader_copy),'current_reader':reader,'initial_hunter':current,'initial_tree':ops.tree(job['pid']),'initial_plist_sha256':sha(PLIST),'python':str(V2/'venvs/hunter/bin/python'),'python_sha256':sha(V2/'venvs/hunter/bin/python'),'launcher_python_sha256':sha(V2/'venv/bin/python'),'hunter_environment_sha256':sha(V2/'config/hunter.environment.json'),'web_environment_sha256':sha(V2/'config/web.environment.json'),'legacy_plan_sha256':sha(LEGACY_PLAN),'during_protection':projection,'web_release':web,'web_tree':projects['web_window']['new_tree'],'web_socket':projects['web_window']['new_socket'],'web_binding':{'path':str(binding),'sha256':sha(binding)},'tool_source_sha256':sha(__file__),'helper_files':{name:sha(ROOT/name) for name in ('release-integration/scripts/takeover_backup.py','release-integration/scripts/takeover_operator.py','release-integration/scripts/projects_first_maintenance.py','release-integration/scripts/night_worker_ops.py','release-integration/scripts/prepare_hunter_directory_maintenance.py')},'prepared_at':utc()}
 immutable(plan);plan['protected_before']=peers(ops,plan);ops.ready(3);atomic(path,plan);print(json.dumps({'state':'PREPARED_HUNTER_ONLY_NOT_EXECUTED','plan':str(path),'sha256':sha(path),'runtime_files':len(files)}))


def stage_reader(plan):
 require(not RELEASE.is_symlink(),'RUNTIME_RELEASE_ALIAS')
 if not RELEASE.exists():
  staging=private_dir(V2/'releases'/('.hunter-f9-stage-'+uuid.uuid4().hex))
  for path,h in plan['runtime_files'].items():
   target=staging/path;private_dir(target.parent);atomic(target,(Path(plan['code_root'])/path).read_bytes());require(sha(target)==h,'RUNTIME_COPY_DRIFT')
  require(not os.path.lexists(RELEASE),'RUNTIME_RELEASE_APPEARED_DURING_COPY');os.rename(staging,RELEASE)
 actual=set()
 for path in RELEASE.rglob('*'):
  require(not path.is_symlink(),'RUNTIME_RELEASE_ALIAS')
  if path.is_file():actual.add(str(path.relative_to(RELEASE)))
 require(actual==set(plan['runtime_files']),'RUNTIME_RELEASE_INVENTORY_DRIFT')
 for path,h in plan['runtime_files'].items():require(sha(private_file(RELEASE/path))==h,'INSTALLED_F9_SOURCE_DRIFT')
 if os.path.lexists(ACCEPTANCE):require(sha(private_file(ACCEPTANCE))==plan['acceptance']['sha256'],'EXISTING_F9_ACCEPTANCE_DRIFT')
 else:atomic(ACCEPTANCE,Path(plan['acceptance']['path']).read_bytes())


def install_reader_plan(plan):
 require(not PLAN_DIR.is_symlink(),'READER_PLAN_ALIAS')
 if not PLAN_DIR.exists():night.render(plan['reader_plan'],PLAN_DIR)
 require(read_json(private_file(PLAN_DIR/'worker.json'))==plan['reader_plan'] and sha(private_file(PLAN_DIR/'night_worker_ops.py'))==sha(Path(night.__file__)),'RENDERED_F9_PLAN_DRIFT')
 require(plistlib.loads(private_file(PLAN_DIR/(LABEL+'.plist')).read_bytes())==expected_job(),'RENDERED_F9_PLIST_DRIFT');night.validate(plan['reader_plan'])


def owner_env(plan):
 return {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','PYTHONPATH':str(RELEASE/'services/hunter-worker/python'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PYTHONSAFEPATH':'1','DATA_ROOT':str(V2/'data'),'HUNTER_DB':str(DATABASE),'HUNTER_V2_MODE':'1','HUNTER_EXTERNAL_IO_ENABLED':'0','HUNTER_REQUIRE_EXTERNAL_IO_DISABLED':'1','HUNTER_DELIVERY_PROTOCOL':'v2-event'}


def owner(plan,ops,name,args):
 ops.fence();out=OUTPUT/(name+'-'+uuid.uuid4().hex+'.json');command([plan['python'],*args],OUTPUT/'owner-cli.private.log',env=owner_env(plan),stdout=out,timeout=60);return out,read_json(out)


def schema(plan,ops):
 code="import json,sys;from hunterradar.migration import inspect;print(json.dumps({'schema':inspect(sys.argv[1])}))"
 return owner(plan,ops,'inspect',['-c',code,str(DATABASE)])[1]['schema']


def wait_lease(ops,timeout=60):
 deadline=time.monotonic()+timeout
 while True:
  ops.fence()
  with closing(sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
   db.execute('PRAGMA query_only=ON');row=db.execute('SELECT expires_at FROM worker_lease WHERE id=1').fetchone()
  if not row or row[0]<=time.time():return
  require(time.monotonic()<deadline,'HUNTER_LEASE_NOT_EXPIRED_NO_DELETE');time.sleep(.2)


def prearm_f9_plist(window,save,ops,plan):
 """A reboot after005 must never auto-launch the old schema4 reader."""
 ops.fence();require(all(original_absent(ops,p) for p in window['tree']),'ORIGINAL_HUNTER_TREE_STILL_ALIVE')
 body=plistlib.dumps(expected_job());expected=hashlib.sha256(body).hexdigest();current=sha(private_file(PLIST))
 if window.get('prearm_intent'):require(window['prearm_intent']['sha256']==expected,'PREARM_BINDING_CHANGED')
 else:require(current==plan['initial_plist_sha256'],'PLIST_CHANGED_BEFORE_F9_PREARM');window['prearm_intent']={'at':utc(),'sha256':expected};save()
 require(current in (plan['initial_plist_sha256'],expected),'UNEXPECTED_PLIST_DURING_PREARM')
 if current!=expected:atomic(PLIST,body)
 require(sha(PLIST)==expected,'F9_PREARM_NOT_DURABLE');window['prearmed']=True;save()


def compatible_restore(state,window,save,ops,plan,version,*,checkpoint=None):
 require(version in (4,5),'UNSUPPORTED_RECOVERY_SCHEMA')
 if state.get('schema5_observed'):require(version==5,'SCHEMA5_STICKY_DOWNGRADE_FORBIDDEN')
 require(all(original_absent(ops,p) for p in window['tree']),'ORIGINAL_HUNTER_TREE_STILL_ALIVE')
 new=version==5
 if new:
  state['schema5_observed']=True;save()
  if not window.get('restore_intent'):
   require(checkpoint and checkpoint['metadata']['user_version']==5 and checkpoint['metadata']['application_id']==0x494B0201,'VERIFIED_SCHEMA5_CHECKPOINT_REQUIRED')
   validate_artifacts(checkpoint);ops.fence();require(fingerprint(checkpoint['artifact']['path'])==fingerprint(DATABASE),'SCHEMA5_CHECKPOINT_NOT_CURRENT');window['bootstrap_schema5_checkpoint']=checkpoint;save()
  else:require(window.get('bootstrap_schema5_checkpoint'),'SCHEMA5_BOOTSTRAP_CHECKPOINT_MISSING');validate_artifacts(window['bootstrap_schema5_checkpoint'])
  install_reader_plan(plan)
  expected=sha(PLAN_DIR/(LABEL+'.plist'));body=(PLAN_DIR/(LABEL+'.plist')).read_bytes()
 else:
  require(plan['current_reader']=='legacy4','LEGACY_RECOVERY_NOT_APPROVED');validate_artifacts(window['original_plist']);expected=plan['initial_plist_sha256'];body=Path(window['original_plist']['artifact']['path']).read_bytes();require(hashlib.sha256(body).hexdigest()==expected,'ORIGINAL_HUNTER_PLIST_BACKUP_DRIFT')
 if not ops.job()['loaded']:
  ops.fence();require(not window.get('restore_intent'),'HUNTER_BOOTSTRAP_UNKNOWN_NO_RETRY')
  current=sha(private_file(PLIST));allowed={plan['initial_plist_sha256'],expected}
  if window.get('prearm_intent') and window['prearm_intent']['sha256']==hashlib.sha256(plistlib.dumps(expected_job())).hexdigest():allowed.add(window['prearm_intent']['sha256'])
  require(current in allowed,'HUNTER_PLIST_UNEXPECTED_CHANGE')
  window['restore_intent']={'at':utc(),'schema':version,'expected_plist_sha256':expected};save()
  if current!=expected:atomic(PLIST,body)
  require(sha(PLIST)==expected,'HUNTER_PLIST_CUTOVER_DRIFT');ops.bootstrap()
 else:
  require(window.get('restore_intent') and window['restore_intent']['schema']==version and sha(PLIST)==expected,'UNEXPECTED_LOADED_HUNTER_RESTORE')
 ops.ready();job=ops.job();current=ops.process(job['pid']) if job['pid'] else None
 require(current is not None and current['cwd']==str(V2/'jobs/hunter'),'RESTORED_HUNTER_IDENTITY_MISMATCH')
 window.update(restored=True,restored_at=utc(),reader='f9' if new else 'legacy4',new_process=current,new_tree=ops.tree(job['pid']));save()


def verify_apply(result):
 def identity(row):
  require(isinstance(row,dict) and row.get('protocol')=='hunter-takeover-package-v2' and row.get('kind')=='directory' and row.get('package_sha256')==PACKAGE_SHA and row.get('execution_id')=='IKUN-ONLY-2026-10-16','OWNER_DIRECTORY_RECEIPT_MISMATCH')
  require(all(type(row.get(k)) is int and row[k]==0 for k in ('network_requests','watch_writes','notifications','commands','public_events')),'OWNER_SIDE_EFFECT_COUNTER_NONZERO')
 identity(result);duplicate=result.get('duplicate_package');require(type(duplicate) is bool,'OWNER_DUPLICATE_FLAG_INVALID')
 keys=('new_business_rows','new_private_facts','new_private_receipts');expected=(0,0,0) if duplicate else (88,6575,6575)
 require(all(type(result.get(k)) is int for k in keys) and tuple(result[k] for k in keys)==expected,'OWNER_DIRECTORY_COUNTS_MISMATCH')
 if duplicate:
  original=result.get('original_result');identity(original)
  require(original.get('duplicate_package') is False and tuple(original.get(k) for k in keys)==(88,6575,6575),'ORIGINAL_DIRECTORY_COUNTS_MISMATCH_CANNOT_WASH_WITH_REPLAY')


def verify_persisted_run(path,result):
 package=read_json(PACKAGE)
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
  db.execute('PRAGMA query_only=ON');rows=db.execute('SELECT source_sha256,ownership_sha256,projects_sha256,report_json FROM hunter_takeover_runs WHERE package_sha256=?',(PACKAGE_SHA,)).fetchall()
 require(len(rows)==1 and rows[0][:3]==(package['source_sha256'],package['ownership_sha256'],'not-applicable:directory-v2'),'PERSISTED_HUNTER_SOURCE_BINDING_MISMATCH')
 original=json.loads(rows[0][3]);verify_apply(original);require(original.get('duplicate_package') is False,'PERSISTED_RUN_IS_NOT_ORIGINAL_RESULT')
 require((result.get('original_result') if result['duplicate_package'] else result)==original,'CLI_RESULT_DIFFERS_FROM_PERSISTED_ORIGINAL_RUN')


def require_rehearsed_seed(path):
 current=fingerprint(path);seed=read_json(REHEARSAL.parent/'before.private.json')
 require(current['user_version']==4 and set(current['tables'])==set(seed['tables']) and all(row==current['tables'][name] for name,row in seed['tables'].items() if name not in ('state','worker_lease')),'CURRENT_HUNTER_REHEARSAL_REQUIRED')


def verify_directory_rows(before_path,after_path):
 with closing(sqlite3.connect(Path(before_path).as_uri()+'?mode=ro',uri=True)) as db:old={row[0] for row in db.execute('SELECT id FROM hunters')}
 with closing(sqlite3.connect(Path(after_path).as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  rows=[row for row in db.execute('SELECT id,enabled,profile_status,user_id,followers,mode,baseline_ready,watch_covered FROM hunters') if row['id'] not in old]
  require(len(rows)==88 and all(row['enabled']==0 and row['profile_status']=='pending' and all(row[k] is None for k in ('user_id','followers','mode')) and row['baseline_ready']==row['watch_covered']==0 for row in rows),'DIRECTORY_ROWS_NOT_EXPECTED_DISABLED_PENDING')


def readonly_status(path,expected):
 require(sha(private_file(path))==expected,'HUNTER_PLAN_HASH_MISMATCH');plan=read_json(path);require(plan['tool_source_sha256']==sha(__file__),'HUNTER_TOOL_CHANGED');immutable(plan)
 before=sha(JOURNAL);data=read_json(JOURNAL);probe=Journal();probe.data=data;probe.validate()
 state=data.get('maintenance_steps',{}).get(PHASE,{});window=(state.get('windows') or [{}])[-1];ops=HunterOps(None);protected=peers(ops,plan);job=ops.job()
 alive=[p['pid'] for p in window.get('tree',[]) if not original_absent(ops,p)];fence='not_checked_while_loaded'
 if not job['loaded']:
  try:ops.fence();fence='clear'
  except SafeFailure as error:fence=str(error)
 require(sha(JOURNAL)==before,'JOURNAL_CHANGED_DURING_HUNTER_READONLY_QUERY')
 result={'state':state.get('state','not_started'),'hunter_loaded':job['loaded'],'hunter_pid':job['pid'],'stop_intent':bool(window.get('stop_intent')),'original_tree_still_alive':alive,'writer_port_fence':fence,'schema5_last_recorded':bool(state.get('schema5_observed')),'actual_schema_not_queried':True,'restore_intent':bool(window.get('restore_intent')),'restored':bool(window.get('restored')),'protected':protected,'actions':0,'runtime_database_connections':0,'journal_written':False}
 print(json.dumps(result));return result


def execute(candidate,path,expected,*,resume_recovered=False):
 require(sha(private_file(path))==expected,'HUNTER_PLAN_HASH_MISMATCH');plan=read_json(path);require(plan['tool_source_sha256']==sha(__file__),'HUNTER_TOOL_CHANGED')
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==candidate and subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/integration' and not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'EXACT_CLEAN_HUNTER_CANDIDATE_REQUIRED')
 require(subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip()=='63e8a2857241c6a76226f21435e40db9736a1e7e','MAIN_CHANGED');immutable(plan);private_dir(OUTPUT);ops=HunterOps(OUTPUT/'commands.private.log')
 with Journal() as journal:
  require('projects' in journal.data.get('migrated_domains',[]),'PROJECTS_FIRST_NOT_COMPLETE')
  state=journal.data.setdefault('maintenance_steps',{}).setdefault(PHASE,{'package_sha256':PACKAGE_SHA,'steps':{},'windows':[]})
  require(state['package_sha256']==PACKAGE_SHA,'HUNTER_PHASE_INPUT_CHANGED')
  def save():journal.data['maintenance_state']=state.get('state','hunter_maintenance_in_progress');journal.save()
  if state.get('state')=='complete':validate_artifacts(state['result']);validate_artifacts(read_json(state['result']['path']));print(json.dumps({'state':'ALREADY_COMPLETE_NO_ACTION','receipt':state['result']['path']}));return
  if state['windows'] and state['windows'][-1].get('restored'):require(resume_recovered and same_process(ops.process(plan['initial_hunter']['pid']),plan['initial_hunter']),'NEW_REVIEWED_HUNTER_PLAN_AND_RESUME_REQUIRED')
  if not state['windows'] or state['windows'][-1].get('restored'):state['windows'].append({})
  window=state['windows'][-1];index=len(state['windows']);save()
  def step(name,fn):
   old=state['steps'].get(name)
   if old and old['state']=='done':validate_artifacts(old['receipt']);data=read_json(old['receipt']['path']);validate_artifacts(data);return data
   directory=private_dir(old['directory'] if old else OUTPUT/(name+'-'+uuid.uuid4().hex));state['steps'][name]={'state':'intent','directory':str(directory)};save();data=fn(directory);validate_artifacts(data);atomic(directory/'receipt.json',data);state['steps'][name]={'state':'done','directory':str(directory),'receipt':artifact(directory/'receipt.json')};save();return data
  def backups(directory):return {name:sqlite_backup(db,private_dir(directory/name),strict_foreign_keys=True) for name,db in DATABASES.items()}
  try:
   peers(ops,plan);online=step('before_online_'+str(index),backups)
   if online['hunter']['metadata']['user_version']==4:require_rehearsed_seed(online['hunter']['artifact']['path'])
   stage_reader(plan)
   if 'original_plist' not in window:require(sha(private_file(PLIST))==plan['initial_plist_sha256'],'HUNTER_PLIST_DRIFT_BEFORE_STOP');window['original_plist']=copy_private(PLIST,OUTPUT/('original-hunter-'+str(index)+'.plist'));save()
   protected_pids={x['pid'] for x in plan['during_protection']['protected_processes'].values()}|{x['pid'] for x in plan['web_tree']}
   stop_owned_job_once(window,save,ops,plan['initial_hunter'],protected_pids,expected_tree=plan['initial_tree']);ops.fence();peers(ops,plan)
   stopped=step('stopped_window_'+str(index),backups);baseline=stopped['hunter']['artifact']['path'];state.setdefault('first_baseline',stopped['hunter']['artifact']);save()
   if stopped['hunter']['metadata']['user_version']==4:require_rehearsed_seed(baseline)
   wait_lease(ops)
   version=schema(plan,ops)
   if state.get('schema5_observed'):require(version==5,'SCHEMA5_STICKY_DOWNGRADE_FORBIDDEN')
   prearm_f9_plist(window,save,ops,plan);state['migration_intent']=state.get('migration_intent') or utc();save()
   if version==4:owner(plan,ops,'migrate',['-m','hunterradar','migrate'])
   require(schema(plan,ops)==5,'OWNER_MIGRATION_NOT_SCHEMA5');state['schema5_observed']=True;save()
   schema5=step('schema5_before_apply_'+str(index),lambda directory:sqlite_backup(DATABASE,private_dir(directory/'hunter'),strict_foreign_keys=True));require(schema5['metadata']['user_version']==5,'SCHEMA5_BACKUP_REQUIRED')
   state['apply_intent']=state.get('apply_intent') or utc();save();apply_path,applied=owner(plan,ops,'apply',['-m','hunterradar.takeover','apply','--package',str(PACKAGE),'--package-sha256',PACKAGE_SHA,'--database',str(DATABASE),'--offline-confirmed']);verify_apply(applied);state['owner_apply_receipt']=artifact(apply_path);save()
   after=step('after_import_'+str(index),backups);preserve_hunter(baseline,after['hunter']['artifact']['path']);preserve_hunter(state['first_baseline']['path'],after['hunter']['artifact']['path']);verify_persisted_run(after['hunter']['artifact']['path'],applied);verify_directory_rows(state['first_baseline']['path'],after['hunter']['artifact']['path'])
   replay_path,replay=owner(plan,ops,'replay',['-m','hunterradar.takeover','apply','--package',str(PACKAGE),'--package-sha256',PACKAGE_SHA,'--database',str(DATABASE),'--offline-confirmed']);verify_apply(replay);verify_persisted_run(after['hunter']['artifact']['path'],replay);require(replay.get('duplicate_package') is True,'HUNTER_REPLAY_NOT_DUPLICATE');require(fingerprint(DATABASE)==fingerprint(after['hunter']['artifact']['path']),'HUNTER_REPLAY_CHANGED_DATABASE')
   peers(ops,plan);compatible_restore(state,window,save,ops,plan,5,checkpoint=after['hunter']);immutable(plan);protected=peers(ops,plan)
   result={'state':'PASS_HUNTER_DIRECTORY_RUNTIME_IMPORT','candidate':candidate,'completed_at':utc(),'source_commit':SOURCE,'package_sha256':PACKAGE_SHA,'owner_apply_receipt':artifact(apply_path),'owner_replay_receipt':artifact(replay_path),'before_online':online,'stopped':stopped,'schema5_before_apply':schema5,'after_import':after,'original_hunter_rows_preserved':True,'non_import_tables_unchanged':True,'same_package_replay_all_fingerprints_unchanged':True,'reader_release':str(RELEASE),'reader_plan':artifact(PLAN_DIR/'worker.json'),'installed_plist_snapshot':copy_private(PLIST,OUTPUT/'installed-hunter-f9.plist'),'installed_plist_sha256':sha(PLIST),'schema_version':5,'schema5_sticky':True,'web_Tracking_and_permanent_protection':protected,'window':window,'Auth_and_Projects_not_targeted_by_owner_cli':True,'new_provider_calls':0,'Watch_writes':0,'next_builds':0,'database_overwrites':0}
   atomic(OUTPUT/'final-receipt.json',result);state.update(state='complete',result=artifact(OUTPUT/'final-receipt.json'));journal.data['migrated_domains']=list(dict.fromkeys([*journal.data.get('migrated_domains',[]),'hunter']));save();print(json.dumps({'state':result['state'],'receipt':str(OUTPUT/'final-receipt.json'),'sha256':sha(OUTPUT/'final-receipt.json')}))
  except BaseException as error:
   recovery='not_needed'
   try:
    if window.get('stopped') and not window.get('restored'):
     immutable(plan);peers(ops,plan);ops.fence();version=schema(plan,ops)
     if state.get('schema5_observed'):require(version==5,'SCHEMA5_STICKY_DOWNGRADE_FORBIDDEN')
     if version==5:
      state['schema5_observed']=True;save();checkpoint=sqlite_backup(DATABASE,private_dir(OUTPUT/('recovery-schema5-'+uuid.uuid4().hex)),strict_foreign_keys=True)
      if state.get('first_baseline'):preserve_hunter(state['first_baseline']['path'],checkpoint['artifact']['path'])
      window['recovery_schema5_checkpoint']=checkpoint;save()
     if version==4 and state.get('first_baseline'):
      before=fingerprint(state['first_baseline']['path']);now=fingerprint(DATABASE);require(before['user_version']==4 and before['tables'].keys()==now['tables'].keys() and all(row==now['tables'][name] for name,row in before['tables'].items() if name!='state'),'SCHEMA4_RECOVERY_ORIGINAL_ROWS_CHANGED');old=stable_state(state['first_baseline']['path']);current=stable_state(DATABASE);require(old==current,'SCHEMA4_RECOVERY_STATE_CHANGED')
     compatible_restore(state,window,save,ops,plan,version,checkpoint=checkpoint if version==5 else None);recovery='f9_schema5_reader_restored' if version==5 else 'legacy_schema4_reader_restored_before_schema5'
   except BaseException:recovery='blocked_keep_hunter_stopped_no_old_reader_or_database_rollback'
   state.update(state='partial_or_failed',last_failure={'at':utc(),'reason':str(error) if isinstance(error,SafeFailure) else type(error).__name__,'recovery':recovery,'schema5_observed':bool(state.get('schema5_observed'))});save();atomic(OUTPUT/('failure-'+uuid.uuid4().hex+'.json'),state['last_failure']);print(json.dumps({'state':'HUNTER_MAINTENANCE_PARTIAL_OR_FAILED',**state['last_failure']}));raise SystemExit(1)


def main():
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--status',action='store_true');mode.add_argument('--execute',action='store_true');parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256');parser.add_argument('--candidate');parser.add_argument('--resume-recovered',action='store_true');args=parser.parse_args()
 if args.prepare:prepare(Path(args.plan));return
 if args.status:require(args.plan_sha256,'HUNTER_PLAN_HASH_REQUIRED');readonly_status(Path(args.plan),args.plan_sha256);return
 require(args.candidate and args.plan_sha256,'EXACT_HUNTER_EXECUTION_BINDINGS_REQUIRED')
 def interrupt(*_):raise SafeFailure('HUNTER_OPERATOR_INTERRUPTED')
 signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt);execute(args.candidate,Path(args.plan),args.plan_sha256,resume_recovered=args.resume_recovered)


if __name__=='__main__':main()
