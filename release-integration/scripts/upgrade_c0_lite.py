#!/usr/bin/env python3
"""Upgrade only the owned new C0-lite label; preserve its previous release and DBs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
import urllib.request
from deploy_c0_lite import ROOT, TARGET, LABEL, MAIN, command, digest, write_private


def atomic(path, value):
    temporary = path.with_name(path.name + '.new-' + str(os.getpid()))
    write_private(temporary, value)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--from-sha', required=True)
    parser.add_argument('--hunter-environment')
    parser.add_argument('--tracking-environment')
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--use-staged-release', action='store_true')
    args = parser.parse_args()
    assert command(['git', 'rev-parse', 'HEAD'], cwd=ROOT) == args.candidate
    assert command(['git', 'branch', '--show-current'], cwd=ROOT) == 'codex/integration'
    assert not command(['git', 'status', '--porcelain'], cwd=ROOT)
    assert command(['git', 'rev-parse', 'main'], cwd=ROOT) == MAIN
    binding = json.loads((ROOT / 'release-integration/c0-lite/evidence/build-binding.json').read_text())
    for path, expected in {**binding['sources'], **binding['compiled']}.items():
        assert digest(ROOT / path) == expected, path
    owner_path = TARGET / 'owner.json'
    owner = json.loads(owner_path.read_text())
    assert owner['thread'] == '01a13c4c-039a-7713-98f4-47c694ed1a9e' and owner['candidate_sha'] == args.from_sha
    env_path = TARGET / 'config/web.environment.json'
    env = json.loads(env_path.read_text())
    assert env['DATA_ROOT'] == str(TARGET / 'data') and env['IKUN_RELEASE_SHA'] == args.from_sha
    assert env['IKUN_AUTH_ORIGIN'] == 'https://v2.ikun.ca' and 'IKUN_AUTH_DEV' not in env
    hunter_web = {}
    if args.hunter_environment:
        from night_worker_ops import inside, private_json
        path = inside(args.hunter_environment, TARGET / 'config')
        assert path == TARGET / 'config/hunter.environment.json'
        hunter = private_json(path)
        assert hunter['DATA_ROOT'] == env['DATA_ROOT'] and hunter['HUNTER_EXTERNAL_IO_ENABLED'] == '0'
        assert hunter['HUNTER_HOST'] == '127.0.0.1' and hunter['HUNTER_PORT'] == '4011'
        assert len(hunter['HUNTER_API_TOKEN']) >= 32 and len(hunter['PROJECTS_INGEST_HUNTER_TOKEN']) >= 32
        hunter_web = {'IKUN_HUNTER_ORIGIN': 'http://127.0.0.1:4011',
                      'HUNTER_API_TOKEN': hunter['HUNTER_API_TOKEN'],
                      'PROJECTS_INGEST_HUNTER_TOKEN': hunter['PROJECTS_INGEST_HUNTER_TOKEN']}
    tracking_web = {}
    if args.tracking_environment:
        from night_worker_ops import inside, private_json
        path = inside(args.tracking_environment, TARGET / 'config')
        assert path == TARGET / 'config/tracking.environment.json'
        tracking = private_json(path)
        config_path = inside(tracking['IKUN_TRACKING_CONFIG'], TARGET / 'config')
        cfg = private_json(config_path)
        assert tracking['DATA_ROOT'] == env['DATA_ROOT'] and tracking['IKUN_TRACKING_EXTERNAL_IO_DISABLED'] == '1'
        assert cfg['remote_enabled'] is False and cfg['dedicated_account'] is False
        assert cfg['host'] == '127.0.0.1' and cfg['port'] == 4012 and not cfg.get('token_file') and not cfg.get('service_token_file')
        assert len(tracking['TRACKING_API_TOKEN']) >= 32
        tracking_web = {'TRACKING_API_URL': 'http://127.0.0.1:4012', 'TRACKING_API_TOKEN': tracking['TRACKING_API_TOKEN'],
                        'IKUN_TRACKING_FIXTURE': '1'}
    plist = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    job = plistlib.loads(plist.read_bytes())
    assert job['Label'] == LABEL and str(TARGET / 'releases' / args.from_sha) == job['WorkingDirectory']
    release = TARGET / 'releases' / args.candidate
    assert not (args.stage_only and args.use_staged_release)
    if not args.use_staged_release:
        assert not release.exists(), 'NEW_RELEASE_ONLY'
        release.mkdir(mode=0o700)
        archive = subprocess.check_output(['git', 'archive', args.candidate], cwd=ROOT)
        subprocess.run(['/usr/bin/tar', '-x', '-C', str(release)], input=archive, check=True)
        for relative in ('modules/auth/integration/preview-only', 'packages/ui/preview', 'packages/ui/review',
                         'services/tracking-worker/python/tests', 'services/tracking-worker/python/integration/tests'):
            if (release / relative).exists(): shutil.rmtree(release / relative)
        for relative in ('node_modules', 'packages/contracts/dist', 'packages/contracts/node_modules', 'packages/runtime/dist',
                     'packages/runtime/node_modules', 'packages/ui/dist', 'packages/ui/node_modules', 'modules/auth/dist',
                     'apps/website/.next', 'apps/website/node_modules', 'services/hunter-worker/dist',
                         'services/hunter-worker/node_modules', 'services/tracking-worker/dist', 'services/tracking-worker/node_modules'):
            source = ROOT / relative
            if source.is_dir():
                shutil.copytree(source, release / relative, symlinks=True,
                            ignore=(lambda path, names: ['cache'] if Path(path) == source and 'cache' in names else []) if relative.endswith('/.next') else None)
        write_private(release / 'c0-staged.json', {'candidate_sha': args.candidate, 'binding_sha256': digest(ROOT / 'release-integration/c0-lite/evidence/build-binding.json')})
    stage = json.loads((release / 'c0-staged.json').read_text())
    assert stage == {'candidate_sha': args.candidate, 'binding_sha256': digest(ROOT / 'release-integration/c0-lite/evidence/build-binding.json')}
    for path, expected in {**binding['sources'], **binding['compiled']}.items():
        assert digest(release / path) == expected, path
    for path in release.rglob('*'):
        if path.is_symlink(): assert release in path.resolve().parents, 'CROSS_CHECKOUT_DEPENDENCY'
    if args.stage_only:
        print(json.dumps({'status': 'STAGED_NO_SERVICE_CHANGE', 'candidate_sha': args.candidate, 'release': str(release)}))
        return
    rollback = TARGET / 'rollbacks' / (args.from_sha + '-' + time.strftime('%Y%m%d-%H%M%S'))
    rollback.mkdir(parents=True, mode=0o700)
    originals = {plist: plist.read_bytes(), env_path: env_path.read_bytes(), owner_path: owner_path.read_bytes()}
    for path, data in originals.items(): write_private(rollback / path.name, data)
    receipt_path = ROOT / 'release-integration/.runtime/c0-lite/deployment.json'
    receipt = json.loads(receipt_path.read_text())
    write_private(rollback / 'deployment.json', receipt)
    domain = 'gui/' + str(os.getuid())
    service = domain + '/' + LABEL
    command(['/bin/launchctl', 'bootout', service])
    for _ in range(80):
        if subprocess.run(['/bin/launchctl', 'print', service], capture_output=True).returncode: break
        time.sleep(.1)
    else: raise RuntimeError('OWNED_NEW_LABEL_DID_NOT_EXIT')
    try:
        env.update(hunter_web)
        env.update(tracking_web)
        env['IKUN_RELEASE_SHA'] = args.candidate
        job['WorkingDirectory'] = str(release)
        job['ProgramArguments'] = ['/usr/bin/env', '-i', *[k + '=' + v for k, v in env.items()],
                                   str(TARGET / 'toolchains/node24/bin/node'), str(release / 'scripts/start-c0-lite.mjs')]
        owner['candidate_sha'] = args.candidate
        atomic(env_path, env); atomic(owner_path, owner); atomic(plist, plistlib.dumps(job))
        command(['/usr/bin/plutil', '-lint', plist]); command(['/bin/launchctl', 'bootstrap', domain, plist])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                with opener.open('http://127.0.0.1:' + env['PORT'] + '/health/ready', timeout=2) as response:
                    if response.status == 200 and json.load(response)['data']['profile'] == 'c0-lite': break
            except (OSError, ValueError): pass
            time.sleep(.3)
        else: raise RuntimeError('NEW_CANDIDATE_NOT_READY')
        artifact = {'candidate_sha': args.candidate, 'build_id': binding['build_id'], 'lock_sha256': binding['lock_sha256'],
                    'node_sha256': digest(TARGET / 'toolchains/node24/bin/node'),
                    'files': {p: h for p, h in binding['compiled'].items()}}
        write_private(release / 'c0-artifact.json', artifact)
        receipt.update(candidate_sha=args.candidate, release=str(release), build_id=binding['build_id'],
                       artifact_sha256=digest(release / 'c0-artifact.json'), previous_candidate=args.from_sha,
                       rollback=str(rollback), upgraded_at=datetime.now(timezone.utc).isoformat())
        atomic(receipt_path, receipt)
        print(json.dumps({'status': 'UPGRADED_LOCAL_ONLY', 'candidate_sha': args.candidate, 'receipt': str(receipt_path)}))
    except Exception:
        subprocess.run(['/bin/launchctl', 'bootout', service], capture_output=True)
        for _ in range(80):
            if subprocess.run(['/bin/launchctl', 'print', service], capture_output=True).returncode: break
            time.sleep(.1)
        for path, data in originals.items(): atomic(path, data)
        command(['/bin/launchctl', 'bootstrap', domain, plist])
        raise


if __name__ == '__main__':
    main()
