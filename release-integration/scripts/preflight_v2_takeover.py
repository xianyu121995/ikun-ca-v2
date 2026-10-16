#!/usr/bin/env python3
"""Read-only maintenance preparation. No live DB connection, stop, import, or publish."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import time
import urllib.request
from takeover_backup import SafeFailure,require,sha,read_json,private_dir,atomic,validate_artifacts,sqlite_counts,utc
from takeover_operator import System,guard as sealed_protection_guard,PLAN as SEALED_STOP_PLAN

ROOT=Path(__file__).resolve().parents[2]
V2=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
MANIFEST=ROOT.parent/'c0-lite-control/var/takeover-execution/final-inputs/source-manifest-v1.json'
MANIFEST_SHA='8f5a453a705dbe0ba4c3957c94098ba05684a95b1ef54ca16243fa90aa8fac1f'
BASE_RELEASE='0ce180c33ea4be350ac57daa7dbfa5b5221e58cb'
APPROVED={
 'projects':('09afbcfd7ba7d809750d4b27c7599c952335b35f','modules/projects/integration/evidence/takeover-rev2-check.json',('inputs',),'evidence_sha256',59),
 'hunter_takeover':('bf94dd0f93a75c2d8c7e8ebc58a642bf698016ac','services/hunter-worker/python/docs/takeover/receipt.json',('file_sha256','preserved_sha256'),None,20),
 'hunter_sample':('613262279996700fd9418b8037cf1eb6ff38551e','services/hunter-worker/python/docs/sample-only/receipt.json',('file_sha256','preserved_sha256'),None,19),
 'tracking_takeover':('70c138d3fcc440a94b19b0ba79f0b3795f6e202e','services/tracking-worker/python/TAKEOVER-EVIDENCE.json',('source_files',),None,67),
}
PROJECTS_RETAINED_XML={'modules/projects/artifacts/pytest-takeover-r2-initial.xml','modules/projects/artifacts/pytest-takeover-r2-final.xml','modules/projects/artifacts/pytest-takeover-r2-source-final.xml'}
TRACKING_DOCS='9c3a2c2cfe88bdc0025c73afd058f4c5efb94fe4'
def git_blob(commit,path):
 require(re.fullmatch('[0-9a-f]{40}',commit) is not None and not Path(path).is_absolute() and '..' not in Path(path).parts,'UNSAFE_GIT_INPUT')
 result=subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True);require(result.returncode==0,'APPROVED_GIT_OBJECT_MISSING');return result.stdout
def bytes_sha(value):
 import hashlib
 return hashlib.sha256(value).hexdigest()
def approved_inputs():
 result={}
 for domain,(commit,path,fields,evidence_field,count) in APPROVED.items():
  receipt_commit=TRACKING_DOCS if domain=='tracking_takeover' else commit
  raw=git_blob(receipt_commit,path);receipt=json.loads(raw);sources={}
  for field in fields:
   for relative,expected in receipt[field].items():
    require(relative not in sources or sources[relative]==expected,'CONFLICTING_OWNER_SOURCE_BINDING');sources[relative]=expected
  require(len(sources)==count,'OWNER_INPUT_COUNT_CHANGED')
  for relative,expected in sources.items():require(bytes_sha(git_blob(commit,relative))==expected,'OWNER_GIT_SOURCE_HASH_MISMATCH')
  evidence=receipt[evidence_field] if evidence_field else {};retained=[]
  for relative,expected in evidence.items():
   if domain=='projects' and relative in PROJECTS_RETAINED_XML:
    file=ROOT.parent/'projects'/relative;require(sha(file)==expected,'OWNER_RETAINED_EVIDENCE_DRIFT');retained.append(relative)
   else:require(bytes_sha(git_blob(commit,relative))==expected,'OWNER_EVIDENCE_HASH_MISMATCH')
  if domain=='tracking_takeover':
   for key in ('log','junit','focused_log','focused_junit','node_log','query_log'):
    row=receipt['pytest'][key];relative=row['path'];require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'UNSAFE_OWNER_EVIDENCE_PATH');file=ROOT.parent/'tracking-worker/services/tracking-worker/python'/relative;require(sha(file)==row['sha256'],'TRACKING_RETAINED_EVIDENCE_DRIFT');retained.append(relative)
  result[domain]={'commit':commit,'receipt_commit':receipt_commit,'receipt_path':path,'receipt_sha256':bytes_sha(raw),'source_count_verified':len(sources),'evidence_count_verified':len(evidence)+(6 if domain=='tracking_takeover' else 0),'retained_owner_evidence_paths':retained,'source_sha256':sources,'sample_execution_authorized_here':False}
 return result
def source_inputs(path=MANIFEST,expected=MANIFEST_SHA):
 require(sha(path)==expected,'FINAL_SOURCE_MANIFEST_DRIFT');r=read_json(path)
 require(r.get('contract')=='ikun-takeover-source-manifest-v1' and r.get('execution_id')=='IKUN-ONLY-2026-10-16' and r.get('scope')=='ikun-main' and r.get('status')=='legacy_sources_stopped_final_copies_verified','FINAL_SOURCE_MANIFEST_REQUIRED')
 require(r['postgres']['archive']['sha256']=='d0e25f6472aca37ff408ff4ff8219fb6953ab698e053add40dc14e7f44431d46','FINAL_PG_ARCHIVE_CHANGED')
 count=validate_artifacts(r);operator=r['operator_receipt'];require(sha(operator['path'])==operator['sha256'],'FINAL_OPERATOR_RECEIPT_DRIFT')
 return r,{'path':str(path),'sha256':expected,'assets_hash_verified':count,'pg_dump_sha256':r['postgres']['archive']['sha256'],'historical_watch_is_current_provider_proof':r['historical_watch_snapshot']['current_provider_state_verified']}
def inspect_runtime():
 owner=read_json(V2/'owner.json');require(owner['candidate_sha']==BASE_RELEASE,'V2_RELEASE_CHANGED_REVIEW_REQUIRED');system=System(None);jobs={};identities=set()
 protected=sealed_protection_guard(system,read_json(SEALED_STOP_PLAN))
 for name in ('web','hunter','tracking'):
  label='ca.ikun.v2.c0lite.'+name;result=subprocess.run(['/bin/launchctl','print','gui/'+str(os.getuid())+'/'+label],capture_output=True,text=True)
  match=re.search(r'^\s*pid = (\d+)$',result.stdout,re.M);require(result.returncode==0 and match is not None,'V2_JOB_NOT_RUNNING');pid=int(match[1]);require(pid not in identities,'V2_JOBS_NOT_INDEPENDENT');identities.add(pid)
  plist=Path.home()/'Library/LaunchAgents'/(label+'.plist');cfg=plistlib.loads(plist.read_bytes());require(cfg['Label']==label,'V2_PLIST_IDENTITY_MISMATCH')
  jobs[name]={'label':label,'process':system.process(pid),'tree':system.tree(pid),'plist_sha256':sha(plist),'cwd':cfg['WorkingDirectory'],'KeepAlive':cfg.get('KeepAlive'),'RunAtLoad':cfg.get('RunAtLoad'),'ThrottleInterval':cfg.get('ThrottleInterval')}
  require(jobs[name]['process'] is not None and jobs[name]['process']['cwd']==cfg['WorkingDirectory'],'V2_JOB_CWD_MISMATCH')
 env=read_json(V2/'config/web.environment.json');require(env['DATA_ROOT']==str(V2/'data') and env['IKUN_RELEASE_SHA']==BASE_RELEASE,'V2_PATH_RELEASE_MISMATCH')
 release=V2/'releases'/BASE_RELEASE;binding=read_json(release/'release-integration/c0-lite/evidence/build-binding.json')
 for group in ('sources','compiled'):
  for relative,expected in binding[group].items():require(sha(release/relative)==expected,'V2_SOURCE_BUILD_DRIFT')
 dbs={};seen=set();baseline=read_json(ROOT/'release-integration/night/takeover-stop-acceptance.json')
 final=read_json(baseline['receipt']['path']);verified=validate_artifacts(final);backups=0
 for phase in ('before','after'):
  for row in final[phase]['sqlites'].values():require(sqlite_counts(row['artifact']['path'])==row['metadata'],'SEALED_BACKUP_METADATA_DRIFT');backups+=1
 for name in ('auth','projects','hunter','tracking'):
  path=V2/'data'/name/(name+'.db');s=path.lstat();require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and not any(p.is_symlink() for p in path.parents),'V2_DATABASE_ALIAS_OR_MODE')
  identity=(s.st_dev,s.st_ino);require(identity not in seen,'V2_DATABASE_IDENTITY_COLLISION');seen.add(identity)
  expected=read_json(ROOT/'release-integration/night/takeover-operator-plan.json')['v2_database_identities'][name];require(identity==(expected['device'],expected['inode']),'V2_DATABASE_IDENTITY_CHANGED')
  metadata=final['after']['sqlites']['v2_'+name]['metadata'];dbs[name]={'path':str(path),'device':s.st_dev,'inode':s.st_ino,'mode':'0600','links':1,'last_sealed_application_id':metadata['application_id'],'last_sealed_user_version':metadata['user_version'],'live_database_opened':False}
 web_pids={p['pid'] for p in jobs['web']['tree']};result=subprocess.run(['/usr/sbin/lsof','-U','-a','-p',','.join(map(str,sorted(web_pids))),'-Fpn'],capture_output=True,text=True);require(result.returncode==0,'WEB_IPC_HANDLE_QUERY_FAILED')
 socket_pids={};pid=None
 for line in result.stdout.splitlines():
  if line.startswith('p'):pid=int(line[1:])
  elif line.startswith('n/private/tmp/ikp-') and line.endswith('/p.sock'):socket_pids.setdefault(line[1:],set()).add(pid)
 require(len(socket_pids)==1,'UNIQUE_MANAGED_PROJECTS_IPC_REQUIRED');socket_proofs={}
 for value,holders in socket_pids.items():
  path=Path(value);info=path.lstat();require(path.parent.parent==Path('/private/tmp') and stat.S_IMODE(path.parent.stat().st_mode)==0o700 and stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and holders<=web_pids,'PROJECTS_IPC_SOCKET_NOT_OWNED');socket_proofs['managed_projects']={'path':value,'is_socket':True,'mode':'0600','holder_pids':sorted(holders)}
 require(len(jobs['web']['tree'])>1,'WEB_MANAGED_CHILDREN_MISSING')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));health={}
 for name,port in (('web',4000),('hunter',4011),('tracking',4012)):
  with opener.open('http://127.0.0.1:'+str(port)+'/health/ready',timeout=5) as response:
   require(response.status==200,'V2_NOT_READY');data=json.load(response)['data'];health[name]={'status':200}
   if name=='hunter':require(data['external_io_enabled'] is False,'HUNTER_EXTERNAL_IO_CHANGED');health[name]['external_io_enabled']=False
   if name=='tracking':require(data['external_collection_enabled'] is False,'TRACKING_EXTERNAL_IO_CHANGED');health[name]['external_collection_enabled']=False
 return {'jobs':jobs,'databases':dbs,'ipc_sockets':socket_proofs,'health':health,'release':{'sha':BASE_RELEASE,'build_id':binding['build_id'],'source_hashes_verified':len(binding['sources']),'compiled_hashes_verified':len(binding['compiled'])},'web_environment_sha256':sha(V2/'config/web.environment.json'),'backup_assets_verified':verified,'sealed_sqlite_backups_rechecked':backups,'auth_no_import':True,'no_new_live_backup':True,'protected_before_maintenance':protected,'sealed_guard_scope':'Pre-maintenance only; do not reuse old v2 PID invariants after an approved v2 restart. Permanent old-side protection must remain separate.'}
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();os.umask(0o077)
 output=Path(args.output).absolute();require(not output.exists() and not output.is_symlink(),'OUTPUT_ALREADY_EXISTS');require(output.parent.is_dir() and stat.S_IMODE(output.parent.stat().st_mode)==0o700 and not any(p.is_symlink() for p in output.parents),'PRIVATE_NEW_OUTPUT_REQUIRED')
 try:
  manifest,source=source_inputs();result={'state':'PREPARED_READONLY_NOT_EXECUTION_AUTHORIZATION','captured_at':utc(),'source_manifest':source,'approved_owner_inputs':approved_inputs(),'runtime':inspect_runtime(),'runtime_database_writes':0,'service_mutations':0,'provider_calls':0,'builds':0,'imports':0,'code_files_copied':0,'preflight_source_sha256':sha(__file__)};atomic(output,result)
  print(json.dumps({'state':result['state'],'receipt':str(output),'sha256':sha(output),'approved_sources':{k:v['source_count_verified'] for k,v in result['approved_owner_inputs'].items()},'runtime_database_writes':0,'service_mutations':0}))
 except Exception as error:
  atomic(output,{'state':'PREPARATION_BLOCKED_NO_ACTIONS','captured_at':utc(),'error_class':type(error).__name__,'safe_reason':str(error) if isinstance(error,SafeFailure) else 'READONLY_PRECHECK_FAILED','runtime_database_writes':0,'service_mutations':0});print(json.dumps({'state':'PREPARATION_BLOCKED_NO_ACTIONS','receipt':str(output),'safe_reason':str(error) if isinstance(error,SafeFailure) else type(error).__name__}));raise SystemExit(1)

if __name__=='__main__':main()
