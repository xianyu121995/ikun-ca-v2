#!/usr/bin/env python3
"""Isolated negative launcher cases and real-file activation rollback; launchctl is a substitute."""
import io
import json
import os
from pathlib import Path
import plistlib
import secrets
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from c0_test_fixture import ROOT,NODE,PYTHON
import upgrade_c0_lite as upgrade

CHECKS=[]
def check(value,name):
 CHECKS.append({'check':name,'result':'PASS' if value else 'FAIL'})
 assert value,name

def loader_cases():
 for case in ('wrong_path','permissions','symlink','hardlink','existing_direct_token','invalid_json','invalid_token','oversized_file'):
  with tempfile.TemporaryDirectory(prefix='ikun-ingest-loader-',dir='/private/tmp') as directory:
   root=Path(directory);data=root/'data';data.mkdir();config=root/'config';config.mkdir();path=config/'web.environment.json'
   secret=secrets.token_urlsafe(48);path.write_text(json.dumps({'PROJECTS_INGEST_TRACKING_TOKEN':secret}));path.chmod(0o600)
   env={'PATH':str(NODE.parent)+':/usr/bin:/bin','DATA_ROOT':str(data),'PROJECTS_PYTHON':str(PYTHON),'IKUN_TRACKING_INGEST_ENV_FILE':str(path)}
   expected='PRIVATE_INGEST_ENV_REQUIRED'
   if case=='wrong_path':env['IKUN_TRACKING_INGEST_ENV_FILE']=str(root/'wrong.json');expected='OWNED_INGEST_ENV_REQUIRED'
   elif case=='permissions':path.chmod(0o644)
   elif case=='symlink':other=config/'other.json';path.rename(other);path.symlink_to(other)
   elif case=='hardlink':os.link(path,config/'alias.json')
   elif case=='existing_direct_token':env['PROJECTS_INGEST_TRACKING_TOKEN']=secrets.token_urlsafe(48);expected='INVALID_INGEST_DIRECTION'
   elif case=='invalid_json':path.write_text('{ invalid json');expected='INVALID_INGEST_ENV'
   elif case=='invalid_token':path.write_text(json.dumps({'PROJECTS_INGEST_TRACKING_TOKEN':'short'}));expected='INVALID_INGEST_DIRECTION'
   elif case=='oversized_file':path.write_text(' '*65537)
   result=subprocess.run([str(NODE),'scripts/start-c0-lite.mjs'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10)
   check(result.returncode!=0 and expected in result.stderr and secret not in result.stdout+result.stderr,'launcher_fail_closed_'+case)

def activation_case(failure=None):
 fail=bool(failure)
 with tempfile.TemporaryDirectory(prefix='ikun-ingest-activation-',dir='/private/tmp') as directory:
  root=Path(directory);target=root/'owned';(target/'config').mkdir(parents=True);data=target/'data';data.mkdir()
  candidate='a'*40;previous='19863b2af031fc2592bb6d73b7161efc77b0bd1d'
  owner={'thread':'01a13c4c-039a-7713-98f4-47c694ed1a9e','candidate_sha':previous}
  env={'DATA_ROOT':str(data),'IKUN_RELEASE_SHA':previous,'IKUN_AUTH_ORIGIN':'https://v2.ikun.ca','PORT':'4000','TRACKING_API_TOKEN':'t'*64,'HUNTER_API_TOKEN':'h'*64,'PROJECTS_INGEST_HUNTER_TOKEN':'j'*64}
  owner_path=target/'owner.json';env_path=target/'config/web.environment.json'
  for path,value in [(owner_path,owner),(env_path,env)]:path.write_text(json.dumps(value));path.chmod(0o600)
  home=root/'home';agents=home/'Library/LaunchAgents';agents.mkdir(parents=True)
  plist=agents/(upgrade.LABEL+'.plist');plist.write_bytes(plistlib.dumps({'Label':upgrade.LABEL,'WorkingDirectory':str(target/'releases'/previous),'ProgramArguments':['original-web-command']}));plist.chmod(0o600)
  originals={p:p.read_bytes() for p in (owner_path,env_path,plist)}
  sources={}
  for relative,body in [('modules/projects/candidate/projects_service/tracking_observations.py',b'# isolated test input'),('scripts/start-c0-lite.mjs',b'IKUN_TRACKING_INGEST_ENV_FILE')]:
   p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body);sources[relative]=upgrade.digest(p)
  binding={'sources':sources,'compiled':{},'build_id':'SUBSTITUTE_OPS_TEST_ONLY','lock_sha256':'0'*64}
  binding_path=root/'release-integration/c0-lite/evidence/build-binding.json';binding_path.parent.mkdir(parents=True);binding_path.write_text(json.dumps(binding))
  release=target/'releases'/candidate;release.mkdir(parents=True)
  for relative in sources:p=release/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((root/relative).read_bytes())
  (release/'c0-staged.json').write_text(json.dumps({'candidate_sha':candidate,'binding_sha256':upgrade.digest(binding_path)}))
  node=target/'toolchains/node24/bin/node';node.parent.mkdir(parents=True);node.write_bytes(b'ops fixture only')
  receipt=root/'release-integration/.runtime/c0-lite/deployment.json';receipt.parent.mkdir(parents=True);receipt.write_text(json.dumps({'candidate_sha':previous}))
  commands=[];bootstrap_count=0
  def command(argv,**kwargs):
   nonlocal bootstrap_count
   argv=[str(x) for x in argv];commands.append(argv)
   if argv[:3]==['git','rev-parse','HEAD']:return candidate
   if argv[:3]==['git','rev-parse','main']:return upgrade.MAIN
   if argv[:3]==['git','branch','--show-current']:return 'codex/integration'
   if argv[:3]==['git','status','--porcelain']:return ''
   if argv[:2]==['/bin/launchctl','bootstrap']:
    bootstrap_count+=1
    if failure=='bootstrap' and bootstrap_count==1:raise RuntimeError('SYNTHETIC_BOOTSTRAP_FAILURE')
   return ''
  class Ready(io.BytesIO):status=200
  class Opener:
   def open(self,*args,**kwargs):
    if failure=='ready':raise OSError('SYNTHETIC_NOT_READY')
    return Ready(b'{"data":{"profile":"c0-lite"}}')
  with patch.multiple(upgrade,ROOT=root,TARGET=target,command=command),patch.object(upgrade.Path,'home',return_value=home),patch.object(upgrade.subprocess,'run',return_value=subprocess.CompletedProcess([],1)),patch.object(upgrade.urllib.request,'build_opener',return_value=Opener()),patch.object(upgrade.time,'monotonic',side_effect=[0,1,100]),patch.object(upgrade.time,'sleep',return_value=None),patch.object(sys,'argv',['upgrade','--candidate',candidate,'--from-sha',previous,'--use-staged-release','--enable-tracking-ingest']):
   try:upgrade.main();assert not fail
   except RuntimeError as error:assert fail and str(error)==('SYNTHETIC_BOOTSTRAP_FAILURE' if failure=='bootstrap' else 'NEW_CANDIDATE_NOT_READY')
  snapshots=list((target/'rollbacks').iterdir());assert len(snapshots)==1
  assert all((snapshots[0]/p.name).read_bytes()==body for p,body in originals.items())
  if fail:
   check(all(p.read_bytes()==body for p,body in originals.items()) and bootstrap_count==2 and 'PROJECTS_INGEST_TRACKING_TOKEN' not in json.loads(env_path.read_text()),'activation_'+failure+'_failure_restores_original_env_plist_owner_and_removes_new_direction')
  else:
   changed=json.loads(env_path.read_text());token=changed['PROJECTS_INGEST_TRACKING_TOKEN'];job=plistlib.loads(plist.read_bytes())
   check(set(changed)==set(env)|{'PROJECTS_INGEST_TRACKING_TOKEN'} and len(token)>=32 and token not in env.values() and not any(token in x for x in job['ProgramArguments']) and 'IKUN_TRACKING_INGEST_ENV_FILE='+str(env_path) in job['ProgramArguments'],'activation_success_adds_only_one_private_direction_no_secret_argv')
  check(not any(any(name in x for name in ('c0lite.hunter','c0lite.tracking','c0lite.tunnel')) for argv in commands for x in argv),'activation_'+(failure if fail else 'success')+'_never_manages_other_jobs')

def main():
 out=ROOT/'release-integration/.runtime/tracking-ingest';out.mkdir(mode=0o700,parents=True,exist_ok=True)
 try:loader_cases();activation_case();activation_case('bootstrap');activation_case('ready')
 finally:
  path=out/('operations-tests-'+str(time.time_ns())+'.json');path.write_text(json.dumps({'checks':CHECKS,'real_launchd_calls':0,'real_runtime_writes':0,'production_rollback_executed':False},indent=2)+'\n');path.chmod(0o600)
 print(json.dumps({'state':'PASS_ISOLATED_LOADER_AND_ACTIVATION_RECOVERY','checks':len(CHECKS),'receipt':str(path)}))

if __name__=='__main__':main()
