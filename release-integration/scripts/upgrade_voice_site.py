#!/usr/bin/env python3
"""Upgrade only the owned protected website; both frozen worker jobs and four DBs stay put."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid
from deploy_c0_lite import ROOT,TARGET,MAIN,digest
from deploy_b3_tracking import backups
from deploy_b4_hunter import run,job_pid
from night_worker_ops import private_json
from verify_voice_intake import verify


def worker_files():
    paths=[TARGET/'config/hunter.environment.json',TARGET/'config/tracking.environment.json',
           TARGET/'plans/hunter/75b81a2b5210e41bdf8522467c7fba2a6a6e693c/worker.json',
           TARGET/'plans/tracking/64088893841122491aba508fdb514507db3d9339/worker.json']
    paths.extend(Path.home()/'Library/LaunchAgents'/('ca.ikun.v2.c0lite.'+name+'.plist') for name in ('hunter','tracking'))
    return {str(p):digest(p) for p in paths}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',required=True);args=parser.parse_args()
    assert run(['git','rev-parse','HEAD']).strip()==args.candidate and not run(['git','status','--porcelain']).strip()
    assert run(['git','rev-parse','main']).strip()==MAIN;verify()
    owner=private_json(TARGET/'owner.json');previous='64088893841122491aba508fdb514507db3d9339';assert owner['candidate_sha']==previous
    before_files=worker_files();before_pids={name:job_pid('ca.ikun.v2.c0lite.'+name) for name in ('web','hunter','tracking')};assert all(before_pids.values())
    identities={name:((TARGET/'data'/name/(name+'.db')).stat().st_dev,(TARGET/'data'/name/(name+'.db')).stat().st_ino) for name in ('auth','projects','hunter','tracking')}
    report={'state':'PREPARING','website_candidate':args.candidate,'previous_website':previous,'Hunter_release':'75b81a2b5210e41bdf8522467c7fba2a6a6e693c','Tracking_release':previous,'Cloudflare_changed':False,'old_services_changed':False,'worker_jobs_changed':False,'real_sound':False,'real_provider_calls':0}
    out=ROOT/'release-integration/.runtime/night-voice/deployment.json'
    try:
        report['backup_before']=backups(TARGET/'backups'/('voice-before-'+uuid.uuid4().hex))
        run(['/Users/lvlei/.local/bin/python3.11',ROOT/'release-integration/scripts/upgrade_c0_lite.py','--candidate',args.candidate,'--from-sha',previous],timeout=300)
        after_pids={name:job_pid('ca.ikun.v2.c0lite.'+name) for name in before_pids}
        assert all(after_pids.values()) and after_pids['web']!=before_pids['web']
        assert all(after_pids[name]==before_pids[name] for name in ('hunter','tracking')) and worker_files()==before_files
        for name,identity in identities.items():
            info=(TARGET/'data'/name/(name+'.db')).stat();assert (info.st_dev,info.st_ino)==identity
        binding=json.loads((ROOT/'release-integration/c0-lite/evidence/build-binding.json').read_text())
        report.update(state='PASS_VOICE_PROTECTED_V2_WEB_ONLY_LOCAL',website_candidate=args.candidate,candidate_sha=args.candidate,
                      build_id=binding['build_id'],before_pids=before_pids,after_pids=after_pids,worker_file_sha256=before_files,
                      runtime_plan=str(TARGET/'plans/tracking'/previous/'worker.json'),database_inodes_preserved=True,
                      backup_after=backups(TARGET/'backups'/('voice-after-'+uuid.uuid4().hex)),public_verified=False)
        print(json.dumps({'state':report['state'],'website_candidate':args.candidate,'build_id':binding['build_id'],'worker_PIDs_unchanged':True}))
    except Exception:report['state']='FAILED_PRESERVED_FOR_REPAIR';raise
    finally:out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o600)


if __name__=='__main__':main()
