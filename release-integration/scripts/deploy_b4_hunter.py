#!/usr/bin/env python3
"""Install only the accepted new Hunter job and upgrade the owned protected v2 site."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time
import uuid
import urllib.request

from deploy_c0_lite import ROOT, TARGET, MAIN, digest, write_private
from night_worker_ops import inside, private_json, render, validate, unload
from verify_password10_intake import verify

B4 = '10fe9d73dcf9d2dd296b808e8aaee41308f12112'
CONTROL = '7a90ec281211cc8a307692c8e420cf4b802ce452'
LABEL = 'ca.ikun.v2.c0lite.hunter'
UV = '/Users/lvlei/.local/bin/uv'
PYTHON = '/Users/lvlei/.local/bin/python3.11'


def run(argv, env=None, timeout=180):
    result = subprocess.run([str(x) for x in argv], env=env, cwd=ROOT, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('OWNED_B4_STEP_FAILED_' + Path(str(argv[0])).name)
    return result.stdout.decode()


def job_pid(label):
    result = subprocess.run(['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/' + label], capture_output=True, text=True)
    match = re.search(r'^\s*pid = (\d+)$', result.stdout, re.M)
    return int(match[1]) if result.returncode == 0 and match else None


def backup_databases(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {}
    for domain in ('auth', 'projects', 'hunter'):
        source = inside(TARGET / 'data' / domain / (domain + '.db'), TARGET / 'data')
        if not source.exists():
            continue
        info = source.stat()
        assert info.st_nlink == 1 and info.st_mode & 0o777 == 0o600
        destination = directory / (domain + '.db')
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert not dst.execute('PRAGMA foreign_key_check').fetchall()
        destination.chmod(0o600)
        result[domain] = {'backup': str(destination), 'sha256': digest(destination), 'integrity': 'ok'}
    write_private(directory / 'receipt.json', result)
    return result


def ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:4011/health/ready', timeout=2) as response:
            data = json.load(response)['data']
        assert data['external_io_enabled'] is False and data['source_status'] == '未连接真实来源'
        return data
    except (OSError, ValueError, AssertionError):
        return None


def wait_job(previous=None):
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        pid = job_pid(LABEL)
        status = ready()
        if pid and pid != previous and status:
            return pid, status
        time.sleep(.4)
    raise RuntimeError('NEW_HUNTER_JOB_NOT_READY')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--website-from', required=True)
    parser.add_argument('--seed-local-fixture', action='store_true')
    args = parser.parse_args()
    assert run(['git', 'rev-parse', 'HEAD']).strip() == args.candidate
    assert run(['git', 'rev-parse', 'main']).strip() == MAIN
    assert not run(['git', 'status', '--porcelain']).strip()
    verify()
    guard = json.loads((ROOT / 'release-integration/night/guard-hardening-evidence.json').read_text())
    assert digest(ROOT / 'release-integration/scripts/night_worker_ops.py') == guard['source_sha256']['release-integration/scripts/night_worker_ops.py']
    owner = private_json(TARGET / 'owner.json')
    assert owner['thread'] == '01a13c4c-039a-7713-98f4-47c694ed1a9e' and owner['candidate_sha'] == args.website_from
    binding = json.loads((ROOT / 'release-integration/c0-lite/evidence/build-binding.json').read_text())
    for path, expected in {**binding['sources'], **binding['compiled']}.items():
        assert digest(ROOT / path) == expected, path
    absent = subprocess.run(['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/' + LABEL], capture_output=True, text=True)
    assert absent.returncode != 0 and 'Could not find service' in absent.stderr and LABEL in absent.stderr, 'EXACT_NEW_JOB_ABSENCE_REQUIRED'
    plist = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    assert not plist.exists() and not plist.is_symlink()
    assert not (TARGET / 'data/hunter/hunter.db').exists(), 'ONLY_EXPLICIT_NEW_HUNTER_DATABASE'
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 4011))
    report = {'state': 'PREPARING', 'candidate_sha': args.candidate, 'hunter_source_sha': B4,
              'control_commit': CONTROL, 'new_label': LABEL, 'old_services_changed': False,
              'Cloudflare_changed': False, 'external_collection_enabled': False, 'Tracking': 'NOT_RECEIVED'}
    plan_path = None
    installed = False
    try:
        report['pre_upgrade_backups'] = backup_databases(TARGET / 'backups' / ('b4-before-' + uuid.uuid4().hex))
        config = TARGET / 'config/hunter.environment.json'
        assert not config.exists()
        values = {'DATA_ROOT': str(TARGET / 'data'), 'HUNTER_API_TOKEN': secrets.token_urlsafe(32),
                  'PROJECTS_INGEST_HUNTER_TOKEN': secrets.token_urlsafe(32),
                  'HUNTER_HOST': '127.0.0.1', 'HUNTER_PORT': '4011',
                  'HUNTER_DB': str(TARGET / 'data/hunter/hunter.db'), 'HUNTER_V2_MODE': '1',
                  'HUNTER_TENANT_ID': 'ikun-main', 'HUNTER_ENGINE': 'python',
                  'HUNTER_EXTERNAL_IO_ENABLED': '0', 'HUNTER_REQUIRE_EXTERNAL_IO_DISABLED': '1',
                  'HUNTER_PROJECT_DELIVERY_ENABLED': '1', 'HUNTER_DELIVERY_PROTOCOL': 'v2-event',
                  'HUNTER_PROJECT_TASK_URL': 'http://127.0.0.1:4000/internal/v1/ingest/hunter'}
        write_private(config, values)
        job_cwd = TARGET / 'jobs/hunter'
        job_cwd.mkdir(mode=0o700, parents=True, exist_ok=False)
        venv = TARGET / 'venvs/hunter'
        assert not venv.exists()
        run([UV, 'venv', '--python', PYTHON, venv])
        run([UV, 'pip', 'install', '--offline', '--python', venv / 'bin/python', '-r',
             ROOT / 'services/hunter-worker/python/requirements-lock.txt'])
        run([PYTHON, ROOT / 'release-integration/scripts/upgrade_c0_lite.py', '--candidate', args.candidate,
             '--from-sha', args.website_from, '--hunter-environment', config], timeout=300)
        release = TARGET / 'releases' / args.candidate
        init_env = {**values, 'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1',
                    'PYTHONPATH': str(release / 'services/hunter-worker/python'), 'PYTHONDONTWRITEBYTECODE': '1'}
        run([venv / 'bin/python', '-m', 'hunterradar', 'init'], env=init_env)
        if args.seed_local_fixture:
            # Authorized offline fixture only, before this new job has ever been loaded.
            code = 'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from accept_b4_site import seed_hunter;seed_hunter(Path(sys.argv[2]))'
            run([venv / 'bin/python', '-c', code, release / 'release-integration/scripts', TARGET / 'data'], env=init_env)
            report['fixture'] = 'offline synthetic discovery named 本地验收夹具 C0 Hunter; no provider or HTTP fixture endpoint'
        manifest = json.loads((ROOT / 'services/hunter-worker/python/integration/RECEIVING-B4.json').read_text())
        runtime = {row['source']: row['sha256'] for row in manifest['files'] if row['kind'] in ('runtime', 'explicit_migration', 'dependency_lock')}
        runtime['services/hunter-worker/package.json'] = digest(ROOT / 'services/hunter-worker/package.json')
        runtime['services/hunter-worker/dist/main.js'] = manifest['compiled_entry_sha256']
        node = TARGET / 'toolchains/node24/bin/node'
        argv = [str(node), str(release / 'services/hunter-worker/dist/main.js')]
        receipt = TARGET / 'config' / ('hunter.accepted.' + args.candidate + '.json')
        write_private(receipt, {'accepted_frozen': True, 'worker': 'hunter', 'source_commit': B4, 'control_commit': CONTROL,
                                'runtime_sha256': runtime, 'argv': argv, 'executable_sha256': digest(node),
                                'database_user_version': 4, 'database_application_id': 0x494B0201})
        plan = {'worker': 'hunter', 'accepted_frozen': True, 'candidate_sha': args.candidate,
                'source_commit': B4, 'control_commit': CONTROL, 'release': str(release),
                'acceptance_file': str(receipt), 'acceptance_sha256': digest(receipt),
                'environment_file': str(config), 'cwd': str(job_cwd), 'argv': argv, 'runtime_sha256': runtime}
        validate(plan)
        parent = TARGET / 'plans/hunter'
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = parent / args.candidate
        result = render(plan, destination)
        plan_path = Path(result['plan'])
        write_private(plist, (destination / plist.name).read_bytes())
        run(['/usr/bin/plutil', '-lint', plist])
        run(['/bin/launchctl', 'bootstrap', 'gui/' + str(os.getuid()), plist])
        installed = True
        pid, status = wait_job()
        website_pid = job_pid('ca.ikun.v2.c0lite.web')
        run(['/bin/launchctl', 'kill', 'SIGKILL', 'gui/' + str(os.getuid()) + '/' + LABEL])
        recovered_pid, status = wait_job(pid)
        assert job_pid('ca.ikun.v2.c0lite.web') == website_pid, 'WORKER_CRASH_MUST_NOT_RESTART_WEBSITE'
        connections = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(recovered_pid), '-i', '-n', '-P', '-Fn'], capture_output=True, text=True).stdout.splitlines()
        peers = [line[1:] for line in connections if line.startswith('n')]
        assert peers and all(peer.startswith(('127.0.0.1:', '[::1]:')) for peer in peers), 'NON_LOOPBACK_WORKER_CONNECTION'
        report.update(state='PASS_NEW_HUNTER_LOCAL_JOB', installed=True, first_pid=pid, recovered_pid=recovered_pid,
                      keepalive_recovered=True, website_pid_unchanged=True, readiness=status, network_peers=peers,
                      runtime_plan=str(plan_path), release=str(release), build_id=binding['build_id'],
                      backup_after=backup_databases(TARGET / 'backups' / ('b4-after-' + uuid.uuid4().hex)),
                      public_verified=False)
        print(json.dumps({'state': report['state'], 'candidate_sha': args.candidate, 'pid': recovered_pid,
                          'external_collection_enabled': False, 'public_verified': False}))
    except Exception:
        report['state'] = 'FAILED_PRESERVED_FOR_REPAIR'
        if installed and plan_path:
            report['module_rollback'] = unload(plan_path)
        raise
    finally:
        output = ROOT / 'release-integration/.runtime/night-b4/deployment.json'
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        output.chmod(0o600)


if __name__ == '__main__':
    main()
