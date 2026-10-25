"""Run local module regressions and a build; never starts production or calls providers."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    version = subprocess.check_output([str(args.node), '--version'], text=True).strip()
    if not version.startswith('v24.'):
        parser.error('Node 24 is required')
    env = dict(os.environ, PATH=str(args.node.parent)+os.pathsep+os.environ.get('PATH', ''),
               PYTHONDONTWRITEBYTECODE='1', NEXT_TELEMETRY_DISABLED='1',
               OPENNEWS_TOKEN='', TWITTERAPI_IO_API_KEY='', HUNTER_EXTERNAL_IO_ENABLED='0',
               IKUN_AI_CONFIG=str(root/'.runtime/handover-no-ai.json'))
    imports = ['release-integration/handover', 'packages/runtime/python', 'services/hunter-worker/python',
               'services/tracking-worker/python', 'modules/projects/candidate']
    env['PYTHONPATH'] = os.pathsep.join(str(root/p) for p in imports)
    pytest = [str(args.python), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'handover_offline_guard']
    steps = [('prepare-shared', ['pnpm', 'build:shared']), ('prepare-auth', ['pnpm', 'build:auth'])]
    steps += [(name, pytest+[path]) for name, path in (
        ('runtime-python', 'packages/runtime/python/tests'),
        ('hunter', 'services/hunter-worker/python/tests'),
        ('tracking', 'services/tracking-worker/python/tests'),
        ('release-python', 'release-integration/tests'),
        ('desktop-auth', 'release-integration/lightsail/test_auth_remote.py'))]
    archived_projects = ['test_browser.py', 'test_b2_browser.py', 'test_b2_lifecycle.py']
    steps.insert(5, ('projects', pytest+['modules/projects/candidate/tests']+
                   ['--ignore=modules/projects/candidate/tests/'+p for p in archived_projects]))
    for name, pattern in [('auth', 'modules/auth/tests/*.test.mjs'), ('root', 'tests/*.test.mjs'),
                          ('voice', 'packages/ui/src/voice/tests/*.test.mjs'),
                          ('release-node', 'release-integration/tests/*.test.mjs')]:
        steps.append((name, ['env', 'TSX_TSCONFIG_PATH=packages/ui/tsconfig.check.json', str(args.node), '--import', 'tsx', '--test', *map(str, sorted(root.glob(pattern)))]))
    steps += [('ui', ['pnpm', '--filter', '@ikun/ui', 'test']),
              ('typecheck', ['pnpm', 'typecheck']), ('build', ['pnpm', 'build']),
              ('diff-check', ['git', 'diff', '--check'])]
    report = {'checked_at_utc':datetime.now(timezone.utc).isoformat(), 'node':version,
              'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
              'production_touched':False, 'provider_calls':0,
              'archived_preview_suites_not_run':archived_projects, 'results':[]}
    logs = root/'.runtime/handover-test-logs'
    logs.mkdir(parents=True, exist_ok=True)
    for name, command in steps:
        result = subprocess.run(command, cwd=root, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=600)
        (logs/(name+'.log')).write_text(result.stdout)
        report['results'].append({'name':name,'command':command,'exit_code':result.returncode,
                                  'log':str(logs/(name+'.log'))})
        print(name, 'PASS' if result.returncode==0 else 'FAIL', flush=True)
        if result.returncode:
            print(result.stdout[-12000:], flush=True)
            break
    report['passed'] = len(report['results']) == len(steps) and all(r['exit_code']==0 for r in report['results'])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
