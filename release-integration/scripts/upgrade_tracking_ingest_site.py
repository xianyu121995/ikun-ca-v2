#!/usr/bin/env python3
"""Reviewed website-only receiver activation with four-store backups and fixed worker identities."""
import argparse
import json
from pathlib import Path
import plistlib
import stat
import uuid
from deploy_c0_lite import ROOT,TARGET,MAIN,digest
from deploy_b3_tracking import backups
from deploy_b4_hunter import run,job_pid
from night_worker_ops import private_json,validate
from verify_password10_intake import verify

PREVIOUS='19863b2af031fc2592bb6d73b7161efc77b0bd1d'
HUNTER='75b81a2b5210e41bdf8522467c7fba2a6a6e693c'
TRACKING='64088893841122491aba508fdb514507db3d9339'

def workers():
 paths=[TARGET/'config/hunter.environment.json',TARGET/'config/tracking.environment.json',TARGET/'config/tracking/tracking.json']
 paths += [TARGET/'plans'/name/commit/'worker.json' for name,commit in [('hunter',HUNTER),('tracking',TRACKING)]]
 paths += [Path.home()/'Library/LaunchAgents'/('ca.ikun.v2.c0lite.'+name+'.plist') for name in ('hunter','tracking')]
 for name,commit in [('hunter',HUNTER),('tracking',TRACKING)]:validate(private_json(TARGET/'plans'/name/commit/'worker.json'))
 return {str(p):digest(p) for p in paths}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',required=True);args=parser.parse_args()
 assert run(['git','rev-parse','HEAD']).strip()==args.candidate and not run(['git','status','--porcelain']).strip()
 assert run(['git','rev-parse','main']).strip()==MAIN;verify()
 assert private_json(TARGET/'owner.json')['candidate_sha']==PREVIOUS
 old_env=private_json(TARGET/'config/web.environment.json');assert 'PROJECTS_INGEST_TRACKING_TOKEN' not in old_env
 before_files=workers();before_pids={n:job_pid('ca.ikun.v2.c0lite.'+n) for n in ('web','hunter','tracking','tunnel')};assert all(before_pids.values())
 identities={n:((TARGET/'data'/n/(n+'.db')).stat().st_dev,(TARGET/'data'/n/(n+'.db')).stat().st_ino) for n in ('auth','projects','hunter','tracking')}
 out=ROOT/'release-integration/.runtime/tracking-ingest';out.mkdir(mode=0o700,parents=True,exist_ok=True)
 report={'state':'PREPARING','candidate_sha':args.candidate,'previous_website':PREVIOUS,'Hunter_release':HUNTER,'Tracking_release':TRACKING,'runtime_plan':str(TARGET/'plans/tracking'/TRACKING/'worker.json'),'before_pids':before_pids,'worker_files_before':before_files,'real_provider_calls':0,'Cloudflare_changed':False,'old_services_changed':False,'pending_writeback':'BLOCKED_FROZEN_OWNER_GAP','public_verified':False}
 try:
  report['backup_before']=backups(TARGET/'backups'/('tracking-ingest-before-'+uuid.uuid4().hex))
  run(['/Users/lvlei/.local/bin/python3.11',ROOT/'release-integration/scripts/upgrade_c0_lite.py','--candidate',args.candidate,'--from-sha',PREVIOUS,'--enable-tracking-ingest'],timeout=300)
  after_pids={n:job_pid('ca.ikun.v2.c0lite.'+n) for n in before_pids};assert all(after_pids.values()) and after_pids['web']!=before_pids['web']
  assert all(after_pids[n]==before_pids[n] for n in ('hunter','tracking','tunnel')) and workers()==before_files
  for n,identity in identities.items():
   info=(TARGET/'data'/n/(n+'.db')).stat();assert (info.st_dev,info.st_ino)==identity
  env=private_json(TARGET/'config/web.environment.json');assert set(env)==set(old_env)|{'PROJECTS_INGEST_TRACKING_TOKEN'}
  assert all(env[k]==v for k,v in old_env.items() if k!='IKUN_RELEASE_SHA') and env['IKUN_RELEASE_SHA']==args.candidate
  token=env['PROJECTS_INGEST_TRACKING_TOKEN'];assert len(token)>=32 and all(token!=env.get(k) for k in ('TRACKING_API_TOKEN','HUNTER_API_TOKEN','PROJECTS_INGEST_HUNTER_TOKEN','IKUN_PROJECTS_IPC_TOKEN'))
  plist=Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.web.plist';job=plistlib.loads(plist.read_bytes())
  assert stat.S_IMODE(plist.stat().st_mode)==0o600 and not any(token in x for x in job['ProgramArguments'])
  assert 'IKUN_TRACKING_INGEST_ENV_FILE='+str(TARGET/'config/web.environment.json') in job['ProgramArguments']
  binding=json.loads((ROOT/'release-integration/c0-lite/evidence/build-binding.json').read_text())
  receipt=private_json(ROOT/'release-integration/.runtime/c0-lite/deployment.json')
  report.update(state='PASS_WEBSITE_RECEIVER_LOCAL_ACTIVATION',after_pids=after_pids,worker_files_after=before_files,database_identities_preserved=True,build_id=binding['build_id'],backup_after=backups(TARGET/'backups'/('tracking-ingest-after-'+uuid.uuid4().hex)),rollback=receipt['rollback'],new_private_credential_field='PROJECTS_INGEST_TRACKING_TOKEN',secret_in_launchd_arguments=False)
  print(json.dumps({'state':report['state'],'candidate_sha':args.candidate,'build_id':binding['build_id'],'worker_pids_and_files_unchanged':True}))
 except Exception as error:
  report.update(state='FAILED_ACTIVATION_OR_POSTCHECK_REQUIRES_INSPECTION',error_type=type(error).__name__,automatic_rollback_not_assumed=True)
  try:
   report['observed_website_candidate']=private_json(TARGET/'owner.json')['candidate_sha']
   report['observed_pids']={n:job_pid('ca.ikun.v2.c0lite.'+n) for n in before_pids}
   report['observed_rollback_receipt']=private_json(ROOT/'release-integration/.runtime/c0-lite/deployment.json').get('rollback')
  except Exception:report['post_failure_runtime_observation']='UNAVAILABLE'
  raise
 finally:
  path=out/'deployment.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)

if __name__=='__main__':main()
