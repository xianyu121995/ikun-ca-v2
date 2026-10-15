#!/usr/bin/env python3
"""Stage B3, explicitly initialize its new DB, preflight, install its new job, upgrade v2."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request
import uuid

from deploy_c0_lite import ROOT, TARGET, MAIN, digest, write_private
from deploy_b4_hunter import run, job_pid
from night_worker_ops import inside, private_json, render, validate, unload
from verify_password10_intake import verify
from receive_b3 import B3, CONTROL

LABEL = 'ca.ikun.v2.c0lite.tracking'
HUNTER_RELEASE = '75b81a2b5210e41bdf8522467c7fba2a6a6e693c'
UV = '/Users/lvlei/.local/bin/uv'
PYTHON = '/Users/lvlei/.local/bin/python3.11'
OUT = ROOT / 'release-integration/.runtime/night-b3'


def backups(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {}
    for domain in ('auth', 'projects', 'hunter', 'tracking'):
        source = inside(TARGET / 'data' / domain / (domain + '.db'), TARGET / 'data')
        if not source.exists(): continue
        assert source.stat().st_nlink == 1 and source.stat().st_mode & 0o777 == 0o600
        target = directory / (domain + '.db')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            assert dst.execute('pragma integrity_check').fetchone() == ('ok',)
            assert not dst.execute('pragma foreign_key_check').fetchall()
        target.chmod(0o600)
        result[domain] = {'path':str(target), 'sha256':digest(target), 'integrity':'ok'}
    write_private(directory / 'receipt.json', result)
    return result


def ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:4012/health/ready', timeout=2) as response: data = json.load(response)['data']
        assert data['external_collection_enabled'] is False and data['source_state'] == 'unconfigured'
        return data
    except (OSError, ValueError, AssertionError): return None


def wait_job(previous=None):
    deadline = time.monotonic()+70
    while time.monotonic()<deadline:
        pid,status = job_pid(LABEL),ready()
        if pid and pid != previous and status: return pid,status
        time.sleep(.4)
    raise RuntimeError('NEW_TRACKING_JOB_NOT_READY')


def hunter_identity():
    plan = TARGET / 'plans/hunter' / HUNTER_RELEASE / 'worker.json'
    return {str(path):digest(path) for path in (plan, TARGET/'config/hunter.environment.json', Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.hunter.plist')}


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--website-from', required=True)
    args=parser.parse_args()
    assert run(['git','rev-parse','HEAD']).strip()==args.candidate and not run(['git','status','--porcelain']).strip()
    assert run(['git','rev-parse','main']).strip()==MAIN
    verify()
    assert digest(ROOT/'release-integration/scripts/night_worker_ops.py')=='4ac7144929559e2169684e803319cd181fab4dc00cfb5da0885635a031fd9fd0'
    delta=json.loads((ROOT/'release-integration/night/b3-preflight-receiving.json').read_text())
    assert delta['accepted_frozen'] is True and delta['path']=='services/tracking-worker/python/integration/preflight-release.py'
    assert digest(ROOT/delta['path'])==delta['sha256']
    owner=private_json(TARGET/'owner.json')
    assert owner['thread']=='01a13c4c-039a-7713-98f4-47c694ed1a9e' and owner['candidate_sha']==args.website_from
    absent=subprocess.run(['/bin/launchctl','print','gui/'+str(os.getuid())+'/'+LABEL], capture_output=True,text=True)
    assert absent.returncode and 'Could not find service' in absent.stderr and LABEL in absent.stderr
    plist=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
    assert not plist.exists() and not plist.is_symlink() and not (TARGET/'data/tracking/tracking.db').exists()
    with socket.socket() as probe: probe.bind(('127.0.0.1',4012))
    binding=json.loads((ROOT/'release-integration/c0-lite/evidence/build-binding.json').read_text())
    for path,expected in {**binding['sources'],**binding['compiled']}.items(): assert digest(ROOT/path)==expected,path
    preserved_hunter=hunter_identity(); hunter_pid=job_pid('ca.ikun.v2.c0lite.hunter')
    assert hunter_pid
    report={'state':'PREPARING','candidate_sha':args.candidate,'Tracking_source':B3,'control_commit':CONTROL,
            'preflight_delta':delta,'hunter_release':HUNTER_RELEASE,'Cloudflare_changed':False,'old_services_changed':False,
            'external_collection_enabled':False,'real_provider_calls':0,'audio_output':'not invoked'}
    plan_path=None; installed=False
    try:
        report['backup_before']=backups(TARGET/'backups'/('b3-before-'+uuid.uuid4().hex))
        cfg_dir=TARGET/'config/tracking';cfg_dir.mkdir(mode=0o700,exist_ok=False)
        cfg_path=cfg_dir/'tracking.json'
        write_private(cfg_path,{'db_path':str(TARGET/'data/tracking/tracking.db'),'remote_enabled':False,'dedicated_account':False,
                               'host':'127.0.0.1','port':4012,'token_file':'','service_token_file':'','admin_token_file':'','read_token_file':'','auth_session_url':'',
                               'watch_group':'ikun-ca-v2-project-tracking'})
        env_path=TARGET/'config/tracking.environment.json'
        values={'DATA_ROOT':str(TARGET/'data'),'TRACKING_API_TOKEN':secrets.token_urlsafe(32),
                'IKUN_TRACKING_CONFIG':str(cfg_path),'IKUN_TRACKING_EXTERNAL_IO_DISABLED':'1'}
        write_private(env_path,values)
        job_cwd=TARGET/'jobs/tracking';job_cwd.mkdir(mode=0o700,parents=True,exist_ok=False)
        venv=TARGET/'venvs/tracking';assert not venv.exists()
        run([UV,'venv','--python',PYTHON,venv])
        venv.chmod(0o700)
        run([UV,'pip','install','--offline','--python',venv/'bin/python','-r',ROOT/'services/tracking-worker/python/requirements.lock.txt'])
        upgrade=[PYTHON,ROOT/'release-integration/scripts/upgrade_c0_lite.py','--candidate',args.candidate,'--from-sha',args.website_from,'--tracking-environment',env_path]
        run([*upgrade,'--stage-only'],timeout=300)
        release=TARGET/'releases'/args.candidate
        init_env={**values,'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        entry=release/'services/tracking-worker/python/entry.py'
        for operation in ('init','migrate'): run([venv/'bin/python',entry,operation,'--config',cfg_path],env=init_env)
        preflight=json.loads(run([venv/'bin/python','-I','-B',release/delta['path'],'--release-root',release,'--job-cwd',job_cwd,'--config',cfg_path,'--venv-root',venv],env=init_env))
        assert preflight['passed'] is True and preflight['provider_calls']==0
        report['preflight']=preflight
        manifest=json.loads((ROOT/'services/tracking-worker/python/NIGHT-SOURCE-MANIFEST.json').read_text())
        runtime={row['source']:row['sha256'] for row in manifest['source_mapping'] if row['kind']=='runtime'}
        runtime[delta['path']]=delta['sha256']
        runtime['services/tracking-worker/package.json']=digest(ROOT/'services/tracking-worker/package.json')
        runtime['services/tracking-worker/dist/main.js']=manifest['compiled_node_entry']['sha256']
        node=TARGET/'toolchains/node24/bin/node';argv=[str(node),str(release/'services/tracking-worker/dist/main.js')]
        receipt=TARGET/'config'/('tracking.accepted.'+args.candidate+'.json')
        write_private(receipt,{'accepted_frozen':True,'worker':'tracking','source_commit':B3,'control_commit':CONTROL,
                              'preflight_delta':delta,'runtime_sha256':runtime,'argv':argv,'executable_sha256':digest(node),
                              'database_user_version':4,'database_application_id':1229652482,'tracking_config_sha256':digest(cfg_path)})
        plan={'worker':'tracking','accepted_frozen':True,'candidate_sha':args.candidate,'source_commit':B3,'control_commit':CONTROL,
              'release':str(release),'acceptance_file':str(receipt),'acceptance_sha256':digest(receipt),'environment_file':str(env_path),
              'cwd':str(job_cwd),'argv':argv,'runtime_sha256':runtime}
        validate(plan)
        parent=TARGET/'plans/tracking';parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        destination=parent/args.candidate; result=render(plan,destination);plan_path=Path(result['plan'])
        write_private(plist,(destination/plist.name).read_bytes());run(['/usr/bin/plutil','-lint',plist])
        run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),plist]);installed=True
        first_pid,status=wait_job()
        run([*upgrade,'--use-staged-release'],timeout=300)
        website_pid=job_pid('ca.ikun.v2.c0lite.web');assert website_pid
        run(['/bin/launchctl','kill','SIGKILL','gui/'+str(os.getuid())+'/'+LABEL])
        recovered_pid,status=wait_job(first_pid)
        assert job_pid('ca.ikun.v2.c0lite.web')==website_pid and job_pid('ca.ikun.v2.c0lite.hunter')==hunter_pid
        assert hunter_identity()==preserved_hunter
        report.update(state='PASS_PROTECTED_V2_B3_LOCAL_JOB',first_pid=first_pid,recovered_pid=recovered_pid,
                      keepalive_recovered=True,website_pid=website_pid,hunter_pid_preserved=hunter_pid,
                      hunter_files_unchanged=True,readiness=status,runtime_plan=str(plan_path),build_id=binding['build_id'],
                      backup_after=backups(TARGET/'backups'/('b3-after-'+uuid.uuid4().hex)),public_verified=False)
        print(json.dumps({'state':report['state'],'candidate_sha':args.candidate,'tracking_pid':recovered_pid,'website_pid':website_pid,'hunter_pid_unchanged':hunter_pid,'public_verified':False}))
    except Exception:
        report['state']='FAILED_PRESERVED_FOR_REPAIR'
        if installed and plan_path: report['module_rollback']=unload(plan_path)
        raise
    finally:
        path=OUT/'deployment.json';path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');path.chmod(0o600)


if __name__=='__main__': main()
