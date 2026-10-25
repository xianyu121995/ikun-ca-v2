"""Linux service entrypoints; credentials stay in private files, never argv."""
import json
import logging
import logging.handlers
import os
import runpy
import sys
from pathlib import Path

os.umask(0o077)
base = Path('/var/lib/ikun/production')
root = Path('/opt/ikun/releases/ab3b3d768895741f9a4b36d13568ff5de2245ff4').resolve()
role = sys.argv[1]
assert role == 'hunter', 'hunter_only_launcher'
name = {'hunter': 'hunter.live.environment.json', 'tracking': 'tracking.live.environment.json',
        'web': 'web.environment.json', 'projects': 'web.environment.json'}[role]
path = base / 'config' / name
assert path.stat().st_mode & 0o077 == 0, 'private_configuration_required'
env = {**os.environ, **json.loads(path.read_text())}
env.update(HOME='/var/lib/ikun', TZ='Asia/Shanghai', LANG='C.UTF-8',
           PATH='/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin',
           IKUN_AI_CONFIG=str(base/'config/ai.json'), NODE_ENV='production', NEXT_TELEMETRY_DISABLED='1')
for key in list(env):
    if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
        env.pop(key)
if role == 'web':
    env['NODE_OPTIONS'] = '--max-old-space-size=768'
    os.chdir(root/'apps/website')
    node = '/opt/ikun/toolchains/node24/bin/node'
    os.execve(node, [node, str(root/'apps/website/node_modules/next/dist/bin/next'),
                       'start', '--hostname', '127.0.0.1', '--port', '4000'], env)
elif role == 'projects':
    os.chdir(root/'modules/projects/candidate')
    python = '/opt/ikun/venvs/projects/bin/python'
    os.execve(python, [python, str(root/'modules/projects/integration/ipc-entry.py')], env)
else:
    assert (base/'ops/EXTERNAL_MONITORING_APPROVED').is_file(), 'monitoring_not_approved'
    os.environ.clear()
    os.environ.update(env)
    sys.path[:0] = [str(root/'packages/runtime/python'), str(root/'services'/f'{role}-worker/python')]
    os.chdir(base)
    if role == 'tracking':
        handler = logging.handlers.RotatingFileHandler(base/'logs/tracking-target-raw.jsonl',
                                                       maxBytes=8*1024*1024, backupCount=3)
        logger = logging.getLogger('tracking.target.raw')
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        sys.argv = ['tracking', 'serve', '--config', env['IKUN_TRACKING_CONFIG']]
        runpy.run_module('tracking.cli', run_name='__main__')
    else:
        sys.argv = ['hunterradar', 'run']
        runpy.run_module('hunterradar', run_name='__main__')
