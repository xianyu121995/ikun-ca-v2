#!/usr/bin/env python3
"""One reviewed Tracking import window. Original importer/reader; no provider operations."""
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
import subprocess
import time
import urllib.request
import uuid

from takeover_backup import require,sha,private_dir,atomic,artifact,read_json,validate_artifacts,sqlite_backup,copy_private,command,utc,SafeFailure
from takeover_operator import ROOT,V2,JOURNAL,Journal,System,guard,same_process,original_absent
from projects_first_maintenance import fingerprint,stop_web_once,WebOps
from hunter_directory_maintenance import private_file
import night_worker_ops as night

SOURCE='307d6e2cfb6102d21ffb5cfd7146f64ed195681f'
OLD='64088893841122491aba508fdb514507db3d9339'
PHASE='tracking_307d_formal_v1'
LABEL='ca.ikun.v2.c0lite.tracking'
PLIST=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
DATABASES={n:V2/'data'/n/(n+'.db') for n in ('auth','projects','hunter','tracking')}
DATABASE=DATABASES['tracking']
OUTPUT=ROOT/'release-integration/.runtime/v2-maintenance/tracking-only/307d-formal-v1'
INTAKE=ROOT/'release-integration/.runtime/v2-maintenance/tracking-preparation-scratch/intake-1792154126504342000/INTAKE-ONLY.json'
OWNER_EVIDENCE=INTAKE.parent/'owner-final-inputs-evidence.json'
HUNTER=ROOT/'release-integration/.runtime/v2-maintenance/hunter-first/f9-90b-v1/final-receipt.json'
HUNTER_SHA='1e7c15c7eb3f8f737f1a41ae938546a1559356bce86f63589069efc9102faa6c'
RELEASE=V2/'releases'/SOURCE
PLAN_DIR=V2/'plans/tracking'/SOURCE
CONFIG=V2/'config'/('tracking.config.'+SOURCE+'.json')
ENVIRONMENT=V2/'config'/('tracking.environment.'+SOURCE+'.json')
ACCEPTANCE=V2/'config'/('tracking.accepted.'+SOURCE+'.json')
ADMISSIONS=ROOT.parent/'c0-lite-control/var/takeover-execution/input-admissions-v1'
CERTS={
 'boundary':(ADMISSIONS/'tracking-source-boundary-root-review.json','0cd2dba4f4fae1467c033d6ade6b3ea054108a0f942ad48fe2c0fdac4bf12fe5'),
 'alias':(ADMISSIONS/'tracking-project-alias-approval-v1.json','ff83ce3e5650112c71dd3f39003f5469da3595e243e1748effe0eaf53db02512'),
 'identity':(ADMISSIONS/'tracking-identity-root-approval-v1.json','e15d62b2f2f7c38061680a913a1609e8a0417f3ffe946d36e0a7a895129ccaed')}


def expected_job():
 return {'Label':LABEL,'ProgramArguments':[str(V2/'venv/bin/python'),'-I',str(PLAN_DIR/'night_worker_ops.py'),'run','--plan',str(PLAN_DIR/'worker.json')],'WorkingDirectory':str(V2/'jobs/tracking'),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'ExitTimeOut':30,'Umask':0o077,'Nice':5,'ProcessType':'Background','StandardOutPath':str(V2/'logs/tracking.log'),'StandardErrorPath':str(V2/'logs/tracking.error.log')}


class TrackingOps(System):
 def job(self):
  r=subprocess.run(['/bin/launchctl','print',self.domain+'/'+LABEL],capture_output=True,text=True,timeout=10)
  if r.returncode:require('Could not find service' in r.stdout+r.stderr,'TRACKING_JOB_QUERY_FAILED');return {'loaded':False,'pid':None}
  found=re.search(r'^\s*pid = (\d+)$',r.stdout,re.M);return {'loaded':True,'pid':int(found[1]) if found else None}
 def bootout(self):command(['/bin/launchctl','bootout',self.domain+'/'+LABEL],self.log,timeout=45)
 def bootstrap(self):command(['/bin/launchctl','bootstrap',self.domain,PLIST],self.log,timeout=45)
 def fence(self):
  require(not self.job()['loaded'],'TRACKING_NOT_STOPPED')
  for p in (DATABASE,Path(str(DATABASE)+'-wal'),Path(str(DATABASE)+'-shm')):
   if p.exists():require(not self.source_write_holders(p),'UNKNOWN_TRACKING_WRITER')
  r=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:4012','-sTCP:LISTEN','-Fp'],capture_output=True,text=True,timeout=10)
  require(r.returncode==1 and not r.stdout.strip() and not r.stderr.strip(),'TRACKING_PORT_OPEN_OR_QUERY_FAILED')
 def ready(self,timeout=30):
  deadline=time.monotonic()+timeout;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  while time.monotonic()<deadline:
   try:
    with opener.open('http://127.0.0.1:4012/health/ready',timeout=2) as r:
     data=json.load(r)['data']
     if r.status==200 and data.get('service')=='tracking' and data.get('external_collection_enabled') is False:return
   except Exception:pass
   time.sleep(.2)
  raise SafeFailure('TRACKING_NOT_READY_HARDOFF')


def peers(ops,plan):
 proof=guard(ops,plan['protection'])
 for p in plan['web_tree']:require(same_process(ops.process(p['pid']),p),'PROTECTED_WEB_CHILD_CHANGED')
 require(WebOps(None).socket_proof(ops.tree(plan['web_tree'][0]['pid']))==plan['web_socket'],'PROTECTED_WEB_SOCKET_CHANGED')
 binding=read_json(plan['web_binding']['path']);require(sha(plan['web_binding']['path'])==plan['web_binding']['sha256'],'PROTECTED_WEB_BINDING_CHANGED')
 for group in ('sources','compiled'):
  for path,h in binding[group].items():require(sha(V2/'releases'/plan['web_release']/path)==h,'PROTECTED_WEB_BUILD_CHANGED')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for service,port in (('website',4000),('hunter',4011)):
  with opener.open('http://127.0.0.1:'+str(port)+'/health/ready',timeout=3) as r:
   data=json.load(r)['data'];require(r.status==200 and data.get('service')==service,'PROTECTED_SERVICE_NOT_READY')
   if service=='hunter':require(data.get('external_io_enabled') is False,'HUNTER_EXTERNAL_IO_CHANGED')
 return proof


def released(path):
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
  db.execute('PRAGMA query_only=ON');row=db.execute('SELECT heartbeat,connection,pong_at FROM runtime WHERE id=1').fetchone()
 require(row is not None and row==(0,'disconnected',None),'TRACKING_GRACEFUL_RELEASE_REQUIRED_NO_SQL_CLEAR')


def owner_args(plan,config,*,apply):
 args=[plan['python'],str(RELEASE/'services/tracking-worker/python/integration/import-takeover.py'),'--config',str(config)]
 for name,arg in (('bundle','bundle'),('map','projects-map'),('ownership','ownership')):
  proof=plan['inputs'][name];args+=['--'+arg,proof['path'],'--'+arg+'-sha256',proof['sha256']]
 for name in ('boundary','alias','identity'):
  proof=plan['certificates'][name];args+=['--recovery-'+name+'-review',proof['path'],'--recovery-'+name+'-review-sha256',proof['sha256']]
 return args+(['--apply'] if apply else [])


def verify_result(result,*,replay=False):
 expected={'accounts':0 if replay else 1,'tweets':0,'ledger':0,'notifications':0}
 require(result.get('passed') is True and result.get('replayed') is replay and result.get('delta')==expected and all(type(x) is int for x in result['delta'].values()),'TRACKING_OWNER_COUNTS_MISMATCH')
 summary=result.get('summary',{});require(summary.get('accounts')=={'input':1,'created':1} and summary.get('tweets')=={'input':0} and summary.get('reason_counts')=={},'TRACKING_ORIGINAL_SUMMARY_NOT_COMPLETE')


def verify_persisted(path,plan,result):
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)) as db:
  rows=db.execute('SELECT key,fingerprint,result FROM receipts WHERE key=? OR key LIKE ?',('tracking.takeover.v1:IKUN-ONLY-2026-10-16','tracking.adoption.v1:%')).fetchall()
 values={}
 for key,expected,raw in rows:
  value=json.loads(raw);canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
  require(hashlib.sha256(canonical.encode()).hexdigest()==expected,'TRACKING_PERSISTED_RECEIPT_CORRUPT');values[key]=value
 bound=values.get('tracking.takeover.v1:IKUN-ONLY-2026-10-16',{});require(bound.get('contract')=='tracking-takeover-receipt-v1' and bound.get('inputs')=={arg:plan['inputs'][name]['sha256'] for name,arg in (('bundle','bundle'),('map','projects_map'),('ownership','ownership'))} and bound.get('summary')==result['summary'],'TRACKING_PERSISTED_BINDING_DIFFERS')
 owned=read_json(plan['inputs']['ownership']['path'])['owned'];require(len(owned)==1,'TRACKING_EXPECTED_ONE_OWNED_WATCH')
 rows=[v for k,v in values.items() if k.startswith('tracking.adoption.v1:') and v.get('ownership_sha256')==plan['inputs']['ownership']['sha256']];require(len(rows)==1,'TRACKING_ADOPTION_NOT_EXACTLY_ONE');adopted=rows[0];proof=owned[0];boundary=adopted.get('recovery_boundary',{})
 require(adopted.get('watch_id')==proof['watch_id'] and adopted.get('flags')==proof['flags'] and adopted.get('groups')==proof['groups'] and adopted.get('x_user_id')==proof['x_user_id'],'TRACKING_ORIGINAL_WATCH_CHANGED')
 require(adopted.get('input_revision')==2 and all(boundary.get(field)==plan['certificates'][name]['sha256'] for name,field in (('boundary','root_review_sha256'),('alias','alias_approval_sha256'),('identity','identity_approval_sha256'))),'TRACKING_RECOVERY_CERTIFICATES_NOT_PERSISTED')


def preserve(before_path,after_path):
 before=fingerprint(before_path);after=fingerprint(after_path)
 require(before['application_id']==after['application_id']==0x494B0202 and before['user_version']==after['user_version']==4 and set(before['tables'])==set(after['tables']),'TRACKING_SCHEMA_CHANGED')
 for name,row in before['tables'].items():
  if name=='feed_meta':continue
  actual=after['tables'][name];require(not (collections.Counter(row['row_hash_counts'])-collections.Counter(actual['row_hash_counts'])),'ORIGINAL_TRACKING_ROWS_CHANGED')
  if name not in ('projects','receipts'):require(row==actual,'NON_IMPORT_TRACKING_TABLE_CHANGED')
 with closing(sqlite3.connect(Path(before_path).as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(Path(after_path).as_uri()+'?mode=ro',uri=True)) as b:
  a.row_factory=b.row_factory=sqlite3.Row;x=dict(a.execute('SELECT * FROM feed_meta').fetchone());y=dict(b.execute('SELECT * FROM feed_meta').fetchone())
 require(x.keys()==y.keys() and all(x[k]==y[k] for k in x if k not in ('last_retention_now_ms','semantic_revision')) and y['last_retention_now_ms']>=x['last_retention_now_ms'] and y['semantic_revision']==x['semantic_revision']+after['tables']['projects']['rows']-before['tables']['projects']['rows'],'TRACKING_FEED_META_CHANGED')


def immutable(plan):
 require(plan['source_commit']==SOURCE and sha(private_file(HUNTER))==HUNTER_SHA,'TRACKING_SOURCE_OR_HUNTER_RECEIPT_CHANGED')
 for name,row in {**plan['inputs'],**plan['certificates']}.items():require(sha(private_file(row['path']))==row['sha256'],'TRACKING_INPUT_CHANGED_'+name)
 for row in plan['assets'].values():validate_artifacts(row)
 for relative,h in plan['runtime_files'].items():require(sha(private_file(Path(plan['code_root'])/relative))==h,'TRACKING_STAGED_SOURCE_CHANGED')
 for relative,h in plan['helper_files'].items():require(sha(ROOT/relative)==h,'TRACKING_HELPER_CHANGED')
 require(sha(plan['python'])==plan['python_sha256'],'TRACKING_PYTHON_CHANGED')
 require(sha(__file__)==plan['tool_source_sha256'],'TRACKING_TOOL_CHANGED')


def prepare(path):
 require(path.parent==OUTPUT and not os.path.lexists(path),'NEW_TRACKING_PLAN_REQUIRED');private_dir(OUTPUT)
 require(sha(HUNTER)==HUNTER_SHA,'HUNTER_ACTUAL_RECEIPT_CHANGED');hunter=read_json(HUNTER);intake=read_json(INTAKE);evidence=read_json(OWNER_EVIDENCE)
 require(intake['source_commit']==evidence['source_commit']==SOURCE,'TRACKING_FROZEN_SOURCE_REQUIRED')
 code=Path(intake['code_root']);files={p:sha(p) for p in code.rglob('*') if p.is_file() and (str(p.relative_to(code)).startswith('services/tracking-worker/python/tracking/') or str(p.relative_to(code)) in ('services/tracking-worker/python/requirements.lock.txt','services/tracking-worker/python/integration/import-takeover.py') or str(p.relative_to(code)).startswith('schemas/tracking/') and p.suffix=='.sql')};files={str(p.relative_to(code)):h for p,h in files.items()}
 for relative,h in files.items():require(subprocess.check_output(['git','show',SOURCE+':'+relative],cwd=ROOT)==(code/relative).read_bytes(),'TRACKING_EXACT_GIT_SOURCE_REQUIRED')
 require(sha(code/'services/tracking-worker/python/requirements.lock.txt')==sha(V2/'releases'/OLD/'services/tracking-worker/python/requirements.lock.txt'),'TRACKING_DEPENDENCY_LOCK_CHANGED')
 oldplan=read_json(V2/'plans/tracking'/OLD/'worker.json');oldenv=read_json(private_file(oldplan['environment_file']));cfg=read_json(private_file(oldenv['IKUN_TRACKING_CONFIG']));require(cfg['remote_enabled'] is False and cfg['dedicated_account'] is False and not cfg['token_file'],'ORIGINAL_TRACKING_NOT_OFF')
 cfg['adopt_only']=True;oldenv['IKUN_TRACKING_CONFIG']=str(CONFIG);oldenv['IKUN_TRACKING_EXTERNAL_IO_DISABLED']='1'
 assets={}
 for name,value in (('config',cfg),('environment',oldenv)):
  p=OUTPUT/(path.stem+'.'+name+'.private.json');require(not p.exists(),'NEW_TRACKING_ASSET_REQUIRED');atomic(p,value);assets[name]=artifact(p)
 python=V2/'venvs/tracking/bin/python';control=subprocess.check_output(['git','rev-parse','0fc573e'],cwd=ROOT,text=True).strip()
 accepted={'accepted_frozen':True,'worker':'tracking','source_commit':SOURCE,'control_commit':control,'runtime_sha256':files,'argv':[str(python),'-m','tracking.cli','serve','--config',str(CONFIG)],'executable_sha256':sha(python),'database_user_version':4,'database_application_id':0x494B0202,'tracking_config_sha256':assets['config']['sha256']}
 p=OUTPUT/(path.stem+'.acceptance.json');atomic(p,accepted);assets['acceptance']=artifact(p)
 reader={'worker':'tracking','accepted_frozen':True,'candidate_sha':SOURCE,'source_commit':SOURCE,'control_commit':control,'release':str(RELEASE),'acceptance_file':str(ACCEPTANCE),'acceptance_sha256':assets['acceptance']['sha256'],'environment_file':str(ENVIRONMENT),'cwd':str(V2/'jobs/tracking'),'argv':accepted['argv'],'runtime_sha256':files,'previous_worker_release':None}
 hplan=read_json(OUTPUT.parent.parent/'hunter-first/f9-90b-v1/execution-plan-v5-stopped-window.json')
 protection=copy.deepcopy(hplan['during_protection']);protection['protected_processes'].pop('v2_Tracking');protection['protected_processes']['v2_Hunter']=hunter['window']['new_process'];protection['protected_files_sha256'].pop(str(PLIST));protection['protected_files_sha256'][str(Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.hunter.plist')]=hunter['installed_plist_sha256']
 for row in (hunter['reader_plan'],):protection['protected_files_sha256'][row['path']]=row['sha256']
 hf=read_json(hunter['reader_plan']['path']);protection['protected_files_sha256'][hf['acceptance_file']]=hf['acceptance_sha256'];protection['protected_files_sha256'][str(Path(hunter['reader_plan']['path']).parent/'night_worker_ops.py')]=sha(Path(night.__file__))
 for relative,h in hf['runtime_sha256'].items():protection['protected_files_sha256'][str(V2/'releases'/hf['candidate_sha']/relative)]=h
 original=plistlib.loads(private_file(PLIST).read_bytes());require(original.get('ProgramArguments') in ([str(V2/'venv/bin/python'),'-I',str(V2/'plans/tracking'/OLD/'night_worker_ops.py'),'run','--plan',str(V2/'plans/tracking'/OLD/'worker.json')],expected_job()['ProgramArguments']),'TRACKING_ORIGINAL_LAUNCHER_CHANGED')
 ops=TrackingOps(None);job=ops.job();require(job['loaded'] and job['pid'],'ORIGINAL_TRACKING_JOB_NOT_RUNNING');process=ops.process(job['pid']);require(process and process['cwd']==str(V2/'jobs/tracking'),'ORIGINAL_TRACKING_CWD_CHANGED')
 plan={'source_commit':SOURCE,'code_root':str(code),'runtime_files':files,'inputs':{k:evidence['files'][k] for k in ('bundle','map','ownership')},'certificates':{k:{'path':str(p),'sha256':h}for k,(p,h)in CERTS.items()},'assets':assets,'reader_plan':reader,'python':str(python),'python_sha256':sha(python),'initial_tracking':process,'initial_tree':ops.tree(job['pid']),'initial_plist_sha256':sha(private_file(PLIST)),'protection':protection,'web_tree':hplan['web_tree'],'web_socket':hplan['web_socket'],'web_binding':hplan['web_binding'],'web_release':hplan['web_release'],'tool_source_sha256':sha(__file__),'helper_files':{p:sha(ROOT/p) for p in ('release-integration/scripts/takeover_backup.py','release-integration/scripts/takeover_operator.py','release-integration/scripts/projects_first_maintenance.py','release-integration/scripts/hunter_directory_maintenance.py','release-integration/scripts/night_worker_ops.py')},'prepared_at':utc()}
 immutable(plan);plan['protected_before']=peers(ops,plan);ops.ready();atomic(path,plan);print(json.dumps({'state':'TRACKING_PREPARED_NOT_EXECUTED','plan':str(path),'sha256':sha(path),'runtime_files':len(files)}))


def stage(plan):
 night.inside(RELEASE,V2/'releases')
 for destination in (CONFIG,ENVIRONMENT,ACCEPTANCE):night.inside(destination,V2/'config')
 if not RELEASE.exists():
  directory=private_dir(V2/'releases'/('.tracking-307d-stage-'+uuid.uuid4().hex))
  for relative,h in plan['runtime_files'].items():p=directory/relative;private_dir(p.parent);atomic(p,(Path(plan['code_root'])/relative).read_bytes());require(sha(p)==h,'TRACKING_COPY_CHANGED')
  require(not os.path.lexists(RELEASE),'TRACKING_RELEASE_APPEARED');os.rename(directory,RELEASE)
 require(not RELEASE.is_symlink() and all(not p.is_symlink() for p in RELEASE.rglob('*')),'TRACKING_RELEASE_ALIAS')
 require({str(p.relative_to(RELEASE)) for p in RELEASE.rglob('*') if p.is_file()}==set(plan['runtime_files']),'TRACKING_RUNTIME_INVENTORY_CHANGED')
 for relative,h in plan['runtime_files'].items():require(sha(private_file(RELEASE/relative))==h,'TRACKING_RUNTIME_CHANGED')
 for name,destination in (('config',CONFIG),('environment',ENVIRONMENT),('acceptance',ACCEPTANCE)):
  row=plan['assets'][name]
  if os.path.lexists(destination):require(sha(private_file(destination))==row['sha256'],'TRACKING_NATIVE_CONFIG_CHANGED')
  else:atomic(destination,Path(row['path']).read_bytes())


def restore(window,save,ops,plan,checkpoint):
 require(all(original_absent(ops,p) for p in window['tree']),'ORIGINAL_TRACKING_TREE_STILL_ALIVE');validate_artifacts(checkpoint);ops.fence() if not ops.job()['loaded'] else None
 if not window.get('restore_intent'):require(fingerprint(checkpoint['artifact']['path'])==fingerprint(DATABASE),'TRACKING_CHECKPOINT_NOT_CURRENT')
 night.inside(PLAN_DIR,V2/'plans/tracking')
 if not PLAN_DIR.exists():night.render(plan['reader_plan'],PLAN_DIR)
 require(read_json(PLAN_DIR/'worker.json')==plan['reader_plan'] and sha(PLAN_DIR/'night_worker_ops.py')==sha(Path(night.__file__)),'TRACKING_NATIVE_PLAN_CHANGED');night.validate(plan['reader_plan'])
 require(plistlib.loads((PLAN_DIR/(LABEL+'.plist')).read_bytes())==expected_job(),'TRACKING_NATIVE_PLIST_CHANGED')
 if not ops.job()['loaded']:
  require(not window.get('restore_intent'),'TRACKING_BOOTSTRAP_UNKNOWN_NO_RETRY');require(sha(private_file(PLIST)) in (plan['initial_plist_sha256'],sha(PLAN_DIR/(LABEL+'.plist'))),'TRACKING_PLIST_FOREIGN_CHANGE')
  window['restore_intent']=utc();save();atomic(PLIST,plistlib.dumps(expected_job()));ops.bootstrap()
 else:require(window.get('restore_intent') and plistlib.loads(private_file(PLIST).read_bytes())==expected_job(),'UNEXPECTED_TRACKING_LOADED')
 ops.ready();current=ops.process(ops.job()['pid']);require(current and current['cwd']==str(V2/'jobs/tracking'),'TRACKING_RESTORED_CWD_CHANGED');window.update(restored=True,restored_at=utc(),new_process=current,new_tree=ops.tree(current['pid']));save()


def readonly_status(path,expected):
 require(sha(private_file(path))==expected,'TRACKING_PLAN_HASH_CHANGED');plan=read_json(path);immutable(plan);before=sha(JOURNAL);data=read_json(JOURNAL);probe=Journal();probe.data=data;probe.validate();state=data.get('maintenance_steps',{}).get(PHASE,{});window=(state.get('windows')or[{}])[-1];ops=TrackingOps(None);protected=peers(ops,plan);job=ops.job()
 require(sha(JOURNAL)==before,'JOURNAL_CHANGED_DURING_TRACKING_STATUS')
 result={'state':state.get('state','not_started'),'tracking_loaded':job['loaded'],'tracking_pid':job['pid'],'stop_intent':bool(window.get('stop_intent')),'restore_intent':bool(window.get('restore_intent')),'restored':bool(window.get('restored')),'protected':protected,'actions':0,'runtime_database_connections':0,'journal_written':False};print(json.dumps(result));return result


def execute(candidate,path,expected,*,resume=False):
 require(sha(private_file(path))==expected,'TRACKING_PLAN_HASH_CHANGED');plan=read_json(path);immutable(plan)
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==candidate and not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'TRACKING_EXACT_CLEAN_CANDIDATE_REQUIRED');require(subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip()=='63e8a2857241c6a76226f21435e40db9736a1e7e','MAIN_CHANGED')
 ops=TrackingOps(OUTPUT/'commands.private.log')
 with Journal() as journal:
  require('hunter' in journal.data['migrated_domains'],'HUNTER_FIRST_REQUIRED');state=journal.data.setdefault('maintenance_steps',{}).setdefault(PHASE,{'windows':[],'steps':{}})
  def save():journal.data['maintenance_state']=state.get('state','tracking_maintenance_in_progress');journal.save()
  if state.get('state')=='complete':validate_artifacts(state['result']);validate_artifacts(read_json(state['result']['path']));print(json.dumps({'state':'ALREADY_COMPLETE_NO_ACTION'}));return
  if state['windows'] and state['windows'][-1].get('restored'):require(resume and same_process(ops.process(plan['initial_tracking']['pid']),plan['initial_tracking']),'NEW_TRACKING_PLAN_AND_RESUME_REQUIRED')
  if not state['windows'] or state['windows'][-1].get('restored'):state['windows'].append({})
  window=state['windows'][-1];index=len(state['windows']);save()
  def step(name,fn):
   previous=state['steps'].get(name)
   if previous and previous['state']=='done':validate_artifacts(previous['receipt']);data=read_json(previous['receipt']['path']);validate_artifacts(data);return data
   directory=private_dir(previous['directory'] if previous else OUTPUT/(name+'-'+uuid.uuid4().hex));state['steps'][name]={'state':'intent','directory':str(directory)};save();data=fn(directory);atomic(directory/'receipt.json',data);state['steps'][name]={'state':'done','directory':str(directory),'receipt':artifact(directory/'receipt.json')};save();return data
  def backups(directory):return {name:sqlite_backup(p,private_dir(directory/name),strict_foreign_keys=True)for name,p in DATABASES.items()}
  try:
   peers(ops,plan);online=step('before_online_'+str(index),backups);stage(plan)
   if 'original_plist' not in window:require(sha(private_file(PLIST))==plan['initial_plist_sha256'],'TRACKING_PLIST_CHANGED');window['original_plist']=copy_private(PLIST,OUTPUT/('original-tracking-'+str(index)+'.plist'));save()
   stop_web_once(window,save,ops,plan['initial_tracking'],{p['pid']for p in plan['protection']['protected_processes'].values()}|{p['pid']for p in plan['web_tree']},expected_tree=plan['initial_tree']);ops.fence();peers(ops,plan);released(DATABASE)
   stopped=step('stopped_window_'+str(index),backups);baseline=stopped['tracking']['artifact']['path']
   environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','PYTHONPATH':str(RELEASE/'services/tracking-worker/python'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','DATA_ROOT':str(V2/'data'),'IKUN_TRACKING_EXTERNAL_IO_DISABLED':'1'}
   def owner(name):
    ops.fence();released(DATABASE);p=OUTPUT/(name+'-'+uuid.uuid4().hex+'.json');command(owner_args(plan,CONFIG,apply=True),OUTPUT/'owner-cli.private.log',env=environment,stdout=p,timeout=60);return p,read_json(p)
   state['apply_intent']=utc();save();applied_path,applied=owner('apply');verify_result(applied,replay=bool(applied.get('replayed')))
   after=step('after_import_'+str(index),backups);preserve(baseline,after['tracking']['artifact']['path']);verify_persisted(after['tracking']['artifact']['path'],plan,applied);replay_path,replayed=owner('replay');verify_result(replayed,replay=True);verify_persisted(after['tracking']['artifact']['path'],plan,replayed);require(fingerprint(DATABASE)==fingerprint(after['tracking']['artifact']['path']),'TRACKING_REPLAY_CHANGED_DATABASE')
   restore(window,save,ops,plan,after['tracking']);protected=peers(ops,plan)
   result={'state':'PASS_TRACKING_RUNTIME_TAKEOVER','candidate':candidate,'source_commit':SOURCE,'completed_at':utc(),'before_online':online,'stopped':stopped,'after_import':after,'owner_apply':artifact(applied_path),'owner_replay':artifact(replay_path),'window':window,'protected':protected,'database_user_version':4,'same_inode':True,'Watch_writes':0,'provider_calls':0,'external_collection_enabled':False,'original_rows_preserved':True,'reader_plan':artifact(PLAN_DIR/'worker.json'),'installed_plist_sha256':sha(PLIST)};atomic(OUTPUT/'final-receipt.json',result);state.update(state='complete',result=artifact(OUTPUT/'final-receipt.json'));journal.data['migrated_domains']=list(dict.fromkeys([*journal.data['migrated_domains'],'tracking']));save();print(json.dumps({'state':result['state'],'receipt':str(OUTPUT/'final-receipt.json'),'sha256':sha(OUTPUT/'final-receipt.json')}))
  except BaseException as error:
   recovery='not_needed'
   try:
    if window.get('stopped') and not window.get('restored'):
     immutable(plan);peers(ops,plan);ops.fence();checkpoint=sqlite_backup(DATABASE,private_dir(OUTPUT/('recovery-'+uuid.uuid4().hex)),strict_foreign_keys=True);restore(window,save,ops,plan,checkpoint);recovery='fixed307d_hardoff_restored'
   except BaseException:recovery='unverified_recovery_no_further_actions'
   state.update(state='partial_or_failed',failure={'at':utc(),'reason':str(error) if isinstance(error,SafeFailure) else type(error).__name__,'recovery':recovery});save();atomic(OUTPUT/('failure-'+uuid.uuid4().hex+'.json'),state['failure']);print(json.dumps({'state':'TRACKING_MAINTENANCE_FAILED',**state['failure']}));raise SystemExit(1)


if __name__=='__main__':
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true');mode.add_argument('--status',action='store_true');parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256');parser.add_argument('--candidate');parser.add_argument('--resume-recovered',action='store_true');args=parser.parse_args()
 if args.prepare:prepare(Path(args.plan))
 elif args.status:
  require(args.plan_sha256,'TRACKING_PLAN_HASH_REQUIRED');readonly_status(Path(args.plan),args.plan_sha256)
 else:
  require(args.plan_sha256 and args.candidate,'TRACKING_EXACT_BINDINGS_REQUIRED')
  def interrupted(*_):raise SafeFailure('TRACKING_OPERATOR_INTERRUPTED')
  signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted);execute(args.candidate,Path(args.plan),args.plan_sha256,resume=args.resume_recovered)
