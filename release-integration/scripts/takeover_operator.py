#!/usr/bin/env python3
"""One claimed legacy shutdown: backup, two exact jobs, one exact SIGTERM, final snapshots."""
from datetime import datetime,timezone
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import subprocess
import tarfile
import time
import traceback
import uuid
from zoneinfo import ZoneInfo
from takeover_backup import SafeFailure,require,utc,sha,private_dir,private_log,atomic,read_json,artifact,check_artifact,validate_artifacts,sqlite_backup,copy_private,source_pg_params,select_source_role,postgres_dump,postgres_restore,command

ROOT=Path(__file__).resolve().parents[2]
OWNER='01a13c4c-039a-7713-98f4-47c694ed1a9e'
MANAGER='01a13c4a-3a35-7132-a8e4-88b32cc50b01'
EXECUTION='IKUN-ONLY-2026-10-16'
CONTROL=ROOT.parent/'c0-lite-control'
JOURNAL=CONTROL/'var/takeover-execution'/(EXECUTION+'.json')
PLAN=ROOT/'release-integration/night/takeover-operator-plan.json'
OUTPUT=ROOT/'release-integration/.runtime/takeover-execution'/EXECUTION
LIVE=Path('/Users/lvlei/Documents/Codex/2026-10-11/codex-web3-workspace-codex-web3-next/outputs/web3-workspace')
TRACK=Path('/Users/lvlei/Documents/ChatGPT/ikun.ca/.runtime/overload-live-tracking')
HUNTER=Path('/Users/lvlei/Documents/ChatGPT/猎手')
V2=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
ALPHA=Path('/Users/lvlei/Documents/ChatGPT/ALPHA哨兵动态监控/data/state.json')
JOB_SPECS={
 'ca.ikun.overload-tracking':{'pid':46545,'started_local':'2026-10-14 20:44:32','cwd':str(TRACK),'missing_entry_allowed':False},
 'com.lvlei.ikun-auto-research':{'pid':38618,'started_local':'2026-10-12 03:23:12','cwd':'/Users/lvlei/.codex/worktrees/ikun-ca-ai-research-audit/ikun.ca','missing_entry_allowed':True},
}
MANUAL={'pid':6466,'parent_pid':6465,'started_at_local':'2026-10-10 18:33:40','cwd':str(HUNTER),'signal':'SIGTERM'}
PROTECTED={'Alpha':9034,'old_supervisor':79489,'old_Postgres':79494,'old_Tunnel':79502,'v2_web':87924,'v2_Hunter':2608,'v2_Tracking':25225,'v2_Tunnel':39523}
SQLITES={'old_hunter':HUNTER/'data/hunter_monitor.db','old_tracking_events':TRACK/'target-events.sqlite','old_tracking_dispatch':TRACK/'dispatch.sqlite',**{'v2_'+n:V2/'data'/n/(n+'.db') for n in ('auth','projects','hunter','tracking')}}

def local_to_utc(value):return datetime.strptime(value,'%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).isoformat()
class System:
 def __init__(self,log):self.log=log;self.domain='gui/'+str(os.getuid())
 def process(self,pid):
  result=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,uid=,lstart=,comm='],env={**os.environ,'TZ':'UTC','LC_ALL':'C'},capture_output=True,text=True)
  if result.returncode:return None
  parts=result.stdout.strip().split(None,8);require(len(parts)==9,'PROCESS_METADATA_INVALID')
  started=datetime.strptime(' '.join(parts[3:8]),'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc).isoformat()
  result=subprocess.run(['/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn'],capture_output=True,text=True)
  paths=[v[1:].removesuffix(' (deleted)') for v in result.stdout.splitlines() if v.startswith('n')]
  return {'pid':int(parts[0]),'ppid':int(parts[1]),'uid':int(parts[2]),'started_utc':started,'executable':parts[8],'cwd':paths[0] if len(paths)==1 else None}
 def tree(self,pid):
  rows=[line.split() for line in subprocess.check_output(['/bin/ps','-axo','pid=,ppid='],text=True).splitlines()];ids={pid}
  while True:
   old=len(ids);ids.update(int(row[0]) for row in rows if len(row)==2 and int(row[1]) in ids)
   if len(ids)==old:break
  return [p for value in sorted(ids) if (p:=self.process(value)) is not None]
 def job(self,label):
  require(label in JOB_SPECS,'UNAPPROVED_STOP_LABEL')
  result=subprocess.run(['/bin/launchctl','print',self.domain+'/'+label],capture_output=True,text=True)
  if result.returncode:
   require('Could not find service' in result.stdout+result.stderr,'LAUNCHCTL_QUERY_FAILED');return {'loaded':False,'pid':None}
  found=re.search(r'^\s*pid = (\d+)$',result.stdout,re.M);return {'loaded':True,'pid':int(found[1]) if found else None}
 def disabled(self,label):
  require(label in JOB_SPECS,'UNAPPROVED_DISABLED_QUERY')
  result=subprocess.run(['/bin/launchctl','print-disabled',self.domain],capture_output=True,text=True);require(result.returncode==0,'DISABLED_QUERY_FAILED')
  found=re.search(r'"'+re.escape(label)+r'"\s*=>\s*(true|false)',result.stdout);return None if not found else found[1]=='true'
 def disable(self,label):
  require(label in JOB_SPECS,'UNAPPROVED_DISABLE');command(['/bin/launchctl','disable',self.domain+'/'+label],self.log,timeout=15)
 def bootout(self,label):
  require(label in JOB_SPECS,'UNAPPROVED_BOOTOUT');command(['/bin/launchctl','bootout',self.domain+'/'+label],self.log,timeout=45)
 def sigterm_hunter(self,expected):
  current=self.process(6466);require(same_process(current,expected) and current['cwd']==str(HUNTER) and current['ppid']==6465,'MANUAL_IDENTITY_CHANGED_BEFORE_SIGNAL');os.kill(6466,signal.SIGTERM)
 def source_write_holders(self,path):
  result=subprocess.run(['/usr/sbin/lsof','-Fpcfa','--',str(path)],capture_output=True,text=True);require(result.returncode==0 or result.returncode==1 and not result.stderr.strip(),'SOURCE_HANDLE_QUERY_FAILED')
  pid=None;holders=[]
  for line in result.stdout.splitlines():
   if line.startswith('p'):pid=int(line[1:])
   elif line in ('aw','au'):holders.append(pid)
  return sorted(set(holders))

def same_process(actual,expected):return actual is not None and all(actual[k]==expected[k] for k in ('pid','ppid','uid','started_utc','executable'))
def original_absent(system,expected):
 current=system.process(expected['pid']);return current is None or current['started_utc']!=expected['started_utc']
def alpha_health():
 runtime=read_json(ALPHA).get('runtime',{});pong=runtime.get('last_pong_at');age=time.time()-pong if isinstance(pong,(int,float)) else None
 require(runtime.get('pid')==9034 and runtime.get('connected') is True and age is not None and -5<=age<=60,'ALPHA_NOT_FRESH_CONNECTED')
 return {'pid':9034,'connected':True,'last_pong_at':pong,'pong_age_seconds':round(age,3),'reconnects':runtime.get('reconnects'),'observed_at':utc(),'new_wss_connections_by_operator':0}

class Journal:
 def __init__(self,path=JOURNAL):
  self.path=Path(path);self.fd=None
 def __enter__(self):
  p=self.path.parent;require(p.is_dir() and stat.S_IMODE(p.stat().st_mode)==0o700,'JOURNAL_DIRECTORY_NOT_PRIVATE')
  self.fd=os.open(p/(self.path.name+'.operator.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
  try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:os.close(self.fd);self.fd=None;raise SafeFailure('ANOTHER_OPERATOR_ACTIVE')
  try:
   info=self.path.lstat();require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'JOURNAL_FILE_NOT_PRIVATE')
   self.data=read_json(self.path);self.digest=sha(self.path);self.validate();return self
  except Exception:
   fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd);self.fd=None;raise
 def __exit__(self,*args):
  if self.fd is not None:fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd)
 def validate(self):
  r=self.data;require(r.get('execution_id')==EXECUTION and r.get('owner_thread')==MANAGER and r.get('operator_thread')==OWNER and r.get('root_operates_stop') is False,'JOURNAL_OPERATOR_OR_EXECUTION_MISMATCH')
  require(set(r.get('stop_jobs',[]))==set(JOB_SPECS) and r.get('approved_manual_stop')==MANUAL,'JOURNAL_EXACT_AUTHORIZATION_MISMATCH')
 def save(self):
  require(sha(self.path)==self.digest,'JOURNAL_CONCURRENT_CHANGE');self.validate();atomic(self.path,self.data);self.digest=sha(self.path)
 def steps(self):return self.data.setdefault('operator_steps',{})
 def mark(self,name,value):
  self.steps()[name]=value
  if name!='complete':self.data['state']='legacy_operator_in_progress'
  self.save()

def checked_target(system,label,plan):
 row=plan['jobs'][label];current=system.job(label);require(current['loaded'] and current['pid']==row['process']['pid'],'STOP_JOB_PID_DRIFT')
 require(same_process(system.process(current['pid']),row['process']),'STOP_JOB_IDENTITY_DRIFT')
 process=system.process(current['pid']);require(process['cwd']==row['process']['cwd'],'STOP_JOB_CWD_DRIFT')
 require(sha(row['plist'])==row['plist_sha256'],'STOP_JOB_PLIST_DRIFT')
 return current

def guard(system,plan):
 observations={}
 for name,expected in plan['protected_processes'].items():
  current=system.process(expected['pid']);require(same_process(current,expected),'PROTECTED_PROCESS_CHANGED_'+name);observations[name]={'pid':current['pid'],'started_utc':current['started_utc']}
 for path,expected in plan['protected_files_sha256'].items():require(sha(path)==expected,'PROTECTED_FILE_CHANGED')
 for name,row in plan['v2_database_identities'].items():
  s=Path(row['path']).stat();require((s.st_dev,s.st_ino,s.st_nlink,stat.S_IMODE(s.st_mode))==(row['device'],row['inode'],1,0o600),'V2_DATABASE_IDENTITY_CHANGED')
 require(read_json(V2/'owner.json')['candidate_sha']=='0ce180c33ea4be350ac57daa7dbfa5b5221e58cb','V2_BASELINE_CHANGED')
 return {'protected':observations,'alpha':alpha_health(),'observed_at':utc()}

def stop_job_once(journal,system,label,plan,*,timeout=60):
 name='stop_job:'+label;state=journal.steps().get(name)
 if state and state.get('state')=='done':
  require(not system.job(label)['loaded'] and all(original_absent(system,p) for p in state['tree']),'RECORDED_STOP_JOB_REAPPEARED');require(system.disabled(label) is True,'RECORDED_DISABLE_CHANGED');return state
 if state and state.get('bootout_intent'):
  require(not system.job(label)['loaded'],'BOOTOUT_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY')
 else:
  checked_target(system,label,plan)
  if state is None:
   tree=system.tree(plan['jobs'][label]['process']['pid']);require(not {p['pid'] for p in tree}&(set(PROTECTED.values())|{6465,6466}),'PROTECTED_PROCESS_IN_STOP_TREE')
   state={'state':'in_progress','previous_disabled_override':system.disabled(label),'tree':tree,'started_at':utc()};journal.mark(name,state)
  if state.get('disable_intent'):
   require(system.disabled(label) is True,'DISABLE_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY')
  elif system.disabled(label) is not True:
   state['disable_intent']=utc();journal.mark(name,state);system.disable(label)
   require(system.disabled(label) is True,'JOB_DISABLE_NOT_CONFIRMED')
  state['disabled_confirmed']=True;journal.mark(name,state)
  checked_target(system,label,plan);tree=system.tree(plan['jobs'][label]['process']['pid']);require(not {p['pid'] for p in tree}&(set(PROTECTED.values())|{6465,6466}),'PROTECTED_PROCESS_IN_STOP_TREE')
  state['tree']=list({(p['pid'],p['started_utc']):p for p in [*state['tree'],*tree]}.values());state['bootout_intent']=utc();journal.mark(name,state);checked_target(system,label,plan);system.bootout(label)
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if not system.job(label)['loaded'] and all(original_absent(system,p) for p in state['tree']):break
  time.sleep(.25)
 else:raise SafeFailure('JOB_NOT_EXITED_NO_FORCE_KILL')
 state.update(state='done',completed_at=utc(),original_disabled_override=state['previous_disabled_override']);journal.data['stopped_jobs']=list(dict.fromkeys([*journal.data.get('stopped_jobs',[]),label]));journal.mark(name,state);return state

def stop_manual_once(journal,system,plan,*,timeout=60):
 name='manual_sigterm:6466';state=journal.steps().get(name);expected=plan['manual_hunter']
 if state and state.get('state')=='done':require(original_absent(system,expected),'RECORDED_MANUAL_PROCESS_REAPPEARED');return state
 if state and state.get('signal_intent'):
  require(original_absent(system,expected),'SIGTERM_OUTCOME_PENDING_NO_AUTOMATIC_RETRY')
 else:
  actual=system.process(6466);require(same_process(actual,expected) and actual['cwd']==str(HUNTER) and actual['ppid']==6465,'MANUAL_HUNTER_IDENTITY_DRIFT')
  state={'state':'in_progress','signal_intent':utc(),'signal':'SIGTERM','pid':6466,'tree':system.tree(6466),'parent_login_before':system.process(6465),'parent_login_signalled':False};journal.mark(name,state);system.sigterm_hunter(expected)
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if original_absent(system,expected) and all(original_absent(system,p) for p in state.get('tree',[expected])):break
  time.sleep(.25)
 else:raise SafeFailure('HUNTER_SIGTERM_PENDING_NO_FORCE_KILL')
 state.update(state='done',completed_at=utc(),parent_login_after=system.process(6465));journal.data['stopped_manual_pids']=list(dict.fromkeys([*journal.data.get('stopped_manual_pids',[]),6466]));journal.mark(name,state);return state

def capture_plan():
 system=System(None);j=read_json(JOURNAL);require(j.get('operator_thread')==OWNER and j.get('approved_manual_stop')==MANUAL,'OPERATOR_HANDOFF_NOT_BOUND')
 jobs={}
 for label,spec in JOB_SPECS.items():
  current=system.job(label);process=system.process(spec['pid']);require(current['pid']==spec['pid'] and process is not None and process['started_utc']==local_to_utc(spec['started_local']),'INITIAL_APPROVED_JOB_IDENTITY_MISMATCH')
  plist=Path.home()/'Library/LaunchAgents'/(label+'.plist');cfg=plistlib.loads(plist.read_bytes());require(cfg['WorkingDirectory']==spec['cwd'],'INITIAL_JOB_CWD_MISMATCH')
  require(process['cwd']==spec['cwd'] or spec['missing_entry_allowed'] and not Path(spec['cwd']).exists(),'INITIAL_PROCESS_CWD_MISMATCH')
  args=cfg.get('ProgramArguments',[]);entries=[v for v in args if v.startswith('/') and v.endswith('.py')]
  jobs[label]={'process':process,'plist':str(plist),'plist_sha256':sha(plist),'cwd':spec['cwd'],'entry_files':[{'path':v,'exists':Path(v).is_file(),'sha256':sha(v) if Path(v).is_file() else None} for v in entries],'restartable_from_existing_entry':all(Path(v).is_file() for v in entries) and bool(entries),'original_disabled_override':system.disabled(label)}
 manual=system.process(6466);require(manual is not None and manual['ppid']==6465 and manual['cwd']==str(HUNTER) and manual['started_utc']==local_to_utc(MANUAL['started_at_local']),'INITIAL_MANUAL_IDENTITY_MISMATCH')
 protected={name:system.process(pid) for name,pid in PROTECTED.items()};require(all(protected.values()),'INITIAL_PROTECTED_PROCESS_MISSING')
 old=read_json(ROOT/'release-integration/night/tracking-ingest-acceptance.json');files=dict(old['worker_files_before'])
 files[str(Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.web.plist')]=sha(Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.web.plist')
 config=TRACK/'config.json';refs=read_json(config);references={k:v for k,v in refs.items() if k.endswith('_file') and isinstance(v,str)}
 pgbin=Path((LIVE/'.runtime/pgbin').read_text().strip());require(pgbin==Path('/opt/homebrew/bin'),'UNEXPECTED_PG_BIN_PATH')
 bins={name:{'path':str(pgbin/name),'sha256':sha(pgbin/name)} for name in ('pg_dump','pg_restore','pg_ctl','initdb','postgres')}
 result={'state':'PENDING_TOOL_REVIEW_NO_OLD_ACTIONS','execution_id':EXECUTION,'authority':'0e875cc910e0b83289d6257ebf68e5af82d7374a','direct_initial_user_message':'01a143aa-3791-7732-9065-410adf6e08f2','captured_at':utc(),'uid':os.getuid(),'jobs':jobs,'manual_hunter':manual,'manual_authorization':MANUAL,'protected_processes':protected,'parent_login':system.process(6465),'protected_files_sha256':files,'v2_database_identities':old['databases'],'tracking_config_sha256':sha(config),'tracking_private_file_references':references,'pgbin':str(pgbin),'pg_binary_sha256':bins,'initial_alpha_health':alpha_health(),'sqlite_sources':{name:{'path':str(path),'device':path.stat().st_dev,'inode':path.stat().st_ino} for name,path in SQLITES.items()},'code_files_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'release-integration/scripts/takeover_backup.py']}}
 atomic(PLAN,result);print(json.dumps({'state':result['state'],'plan':str(PLAN),'job_pids':{k:v['process']['pid'] for k,v in jobs.items()},'manual_sigterm_pid':6466,'protected_processes':len(protected),'old_actions':0}))

def source_files_backup(directory,plan):
 directory=private_dir(directory);receipt=directory/'receipt.json'
 if receipt.exists():
  result=read_json(receipt)
  for row in result['files']:
   if row.get('copied'):check_artifact(row['artifact'])
  for row in result['source_archives']:check_artifact(row)
  return result
 rows=[]
 for label,row in plan['jobs'].items():rows.append(copy_private(row['plist'],directory/(label+'.plist')))
 rows.append(copy_private(TRACK/'config.json',directory/'tracking/config.json'))
 require(sha(TRACK/'config.json')==plan['tracking_config_sha256'],'TRACKING_CONFIG_DRIFT')
 require({k:v for k,v in read_json(TRACK/'config.json').items() if k.endswith('_file') and isinstance(v,str)}==plan['tracking_private_file_references'],'PRIVATE_REFERENCE_DRIFT')
 for key,path in plan['tracking_private_file_references'].items():rows.append(copy_private(path,directory/'tracking'/key))
 for name in ('command-result.json','service-status.json','last-error.json','provisioned.json','supplier-evidence.json','watch-before-private.json','watch-after-private.json','live-verification.json'):
  rows.append(copy_private(TRACK/name,directory/'tracking'/name))
 for pattern in ('.env','config*.json','config*.yaml','config*.yml'):
  for path in HUNTER.glob(pattern):rows.append(copy_private(path,directory/'hunter'/path.name))
 archives=[]
 for name,source in [('tracking_repo',TRACK/'repo'),('hunter_source',HUNTER)]:
  target=directory/(name+'.tar.gz');require(not target.exists(),'PARTIAL_SOURCE_ARCHIVE_REQUIRES_REVIEW')
  with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f,tarfile.open(fileobj=f,mode='w:gz',dereference=False) as tar:
   for path in sorted(source.rglob('*')):
    relative=path.relative_to(source)
    if any(part in ('.git','.venv','venv','node_modules','vendor','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.runtime','data','logs','dist') for part in relative.parts) or path.name=='.env' or path.suffix in ('.db','.sqlite','.dsn','.token','.log','.pyc'):continue
    tar.add(path,arcname=str(relative),recursive=False)
  archives.append(artifact(target))
 result={'files':rows,'source_archives':archives,'ai_missing_entry_explicit':plan['jobs']['com.lvlei.ikun-auto-research']['entry_files'],'ai_restartable_as_is':plan['jobs']['com.lvlei.ikun-auto-research']['restartable_from_existing_entry'],'source_archives_prove_present_disk_bytes_only_not_loaded_process_code':True,'raw_backups_may_include_Alpha_unknown_or_secrets':'private backup only; NOT migration input allowlist','completed_at':utc()};atomic(receipt,result);return result

def run_step(journal,name,fn):
 existing=journal.steps().get(name)
 if existing and existing.get('state')=='done':
  check_artifact(existing['receipt']);result=read_json(existing['receipt']['path']);validate_artifacts(result);return result
 if existing:
  require(existing.get('state')=='intent','UNRECOGNIZED_STEP_STATE');directory=private_dir(existing['directory'])
 else:
  directory=private_dir(OUTPUT/(name+'-'+uuid.uuid4().hex));journal.mark(name,{'state':'intent','directory':str(directory),'started_at':utc()})
 result=fn(directory);validate_artifacts(result);receipt=directory/'operator-receipt.json';atomic(receipt,result);journal.mark(name,{'state':'done','receipt':artifact(receipt),'directory':str(directory),'completed_at':utc()});return result

def backup_phase(journal,system,plan,prefix):
 result={'scope':prefix,'sqlites':{},'started_at':utc()}
 for name,path in SQLITES.items():
  expected=plan['sqlite_sources'][name];info=path.stat();require((info.st_dev,info.st_ino)==(expected['device'],expected['inode']),'SQLITE_SOURCE_CHANGED')
  result['sqlites'][name]=run_step(journal,prefix+'_'+name,lambda directory,p=path,n=name:sqlite_backup(p,directory,static_dispatch=n=='old_tracking_dispatch',strict_foreign_keys=n.startswith('v2_')))
 result['files']=run_step(journal,prefix+'_files',lambda directory:source_files_backup(directory,plan));guard(system,plan)
 pgbin=Path(plan['pgbin'])
 for binary,row in plan['pg_binary_sha256'].items():require(sha(row['path'])==row['sha256'],'PG_BINARY_DRIFT')
 def dump(directory):
  params=source_pg_params(TRACK/'config.json');params,role=select_source_role(params,directory/'role.error.log');row=postgres_dump(params,directory,pgbin);row['read_role_strategy']=role;return row
 result['postgres']=run_step(journal,prefix+'_pg_dump',dump)
 result['restore']=run_step(journal,prefix+'_pg_restore',lambda directory:postgres_restore(result['postgres'],directory,pgbin,protected_pids=[p['pid'] for p in plan['protected_processes'].values()]+[6465,6466,46545,38618]))
 result['guard_after']=guard(system,plan);validate_artifacts(result);result['completed_at']=utc();return result

def execute(candidate):
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==candidate,'EXACT_CANDIDATE_REQUIRED')
 require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/integration' and not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'CLEAN_INTEGRATION_REQUIRED')
 require(subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip()=='63e8a2857241c6a76226f21435e40db9736a1e7e','MAIN_CHANGED')
 plan=read_json(PLAN);require(plan['execution_id']==EXECUTION and plan['uid']==os.getuid(),'PLAN_EXECUTION_MISMATCH')
 for path,expected in plan['code_files_sha256'].items():require(sha(ROOT/path)==expected,'REVIEWED_TOOL_DRIFT')
 private_dir(OUTPUT);system=System(OUTPUT/'commands.error.log')
 with Journal() as journal:
  if journal.steps().get('complete',{}).get('state')=='done':
   record=journal.steps()['complete'];check_artifact(record['receipt']);validate_artifacts(read_json(record['receipt']['path']));print(json.dumps({'state':'ALREADY_COMPLETE_NO_ACTION','receipt':record['receipt']['path']}));return
  require(not journal.data.get('migrated_domains') and journal.data.get('real_sample_executed') is False,'LATER_PHASE_ALREADY_STARTED')
  try:
   baseline=run_step(journal,'baseline',lambda directory:{'guard':guard(system,plan),'targets':{label:checked_target(system,label,plan) for label in JOB_SPECS},'manual_hunter':system.process(6466),'parent_login':system.process(6465),'observed_at':utc()})
   before=backup_phase(journal,system,plan,'before');guard(system,plan)
   for label in JOB_SPECS:
    validate_artifacts(before);stop_job_once(journal,system,label,plan);guard(system,plan)
   validate_artifacts(before);stop_manual_once(journal,system,plan);guard(system,plan)
   for name in ('old_hunter','old_tracking_events','old_tracking_dispatch'):require(not system.source_write_holders(SQLITES[name]),'OLD_SQLITE_HAS_UNEXPECTED_WRITE_HOLDER')
   after=backup_phase(journal,system,plan,'after')
   for label in JOB_SPECS:stop_job_once(journal,system,label,plan)
   stop_manual_once(journal,system,plan)
   result={'state':'APPROVED_LEGACY_PRODUCERS_STOPPED_SNAPSHOTS_VERIFIED','execution_id':EXECUTION,'tool_candidate':candidate,'completed_at':utc(),'stopped_jobs':journal.data['stopped_jobs'],'manual_stopped_pid':6466,'manual_signal':'SIGTERM','parent_login_signalled':False,'parent_login_after':system.process(6465),'before':before,'after':after,'protected_final':guard(system,plan),'migration_executed':False,'new_v2_services_stopped':False,'new_wss_connections':0,'Watch_writes':0,'provider_calls':0,'final_snapshot_scope':'each SQLite online snapshot and PG exported consistent snapshot after three approved producers exited; protected Alpha/PG remain live, not a distributed global transaction','requires_root_owned_filter_before_migration':True,'ai_restart_as_is_blocked':not plan['jobs']['com.lvlei.ikun-auto-research']['restartable_from_existing_entry']}
   p=OUTPUT/'final-receipt.json';atomic(p,result);journal.data['state']='legacy_snapshots_ready_waiting_owner_imports';journal.mark('complete',{'state':'done','receipt':artifact(p),'completed_at':utc()});print(json.dumps({'state':result['state'],'receipt':str(p),'stopped_jobs':result['stopped_jobs'],'manual_stopped_pid':6466,'provider_calls':0}))
  except Exception as error:
   path=OUTPUT/('failure-'+uuid.uuid4().hex+'.log')
   with private_log(path) as f:f.write(traceback.format_exc().encode())
   if sha(journal.path)==journal.digest:
    journal.data['state']='legacy_operator_partial_or_blocked';journal.save()
   summary={'state':'PARTIAL_OR_BLOCKED_NO_BLIND_RETRY','error_class':type(error).__name__,'safe_reason':str(error) if isinstance(error,SafeFailure) else 'SEE_PRIVATE_LOG','stopped_jobs':journal.data.get('stopped_jobs',[]),'manual_stops':journal.data.get('stopped_manual_pids',[]),'private_error_log':str(path),'steps':journal.steps()};atomic(OUTPUT/'failure-summary.json',summary)
   print(json.dumps({k:summary[k] for k in ('state','error_class','safe_reason','stopped_jobs','manual_stops','private_error_log')}));raise SystemExit(1)

def main():
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--capture-plan',action='store_true');group.add_argument('--execute',action='store_true');parser.add_argument('--candidate');args=parser.parse_args()
 if args.capture_plan:capture_plan()
 else:
  require(bool(args.candidate),'CANDIDATE_REQUIRED')
  def interrupt(*_):raise SafeFailure('OPERATOR_INTERRUPTED')
  signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt);execute(args.candidate)

if __name__=='__main__':main()
