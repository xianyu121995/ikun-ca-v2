"""Prepare a private, path-adjusted copy of the approved Mac production configuration."""
import json
import os
import secrets
from pathlib import Path

os.umask(0o077)
source = Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
target = Path('/var/lib/ikun/production')
stage = Path('/private/tmp/ikun-production-config')
stage.mkdir(mode=0o700, exist_ok=True)


def load(name):
    path = source/'config'/name
    assert path.stat().st_mode & 0o077 == 0
    return json.loads(path.read_text())


def rewrite(value):
    if isinstance(value, str):
        return value.replace(str(source), str(target))
    if isinstance(value, dict):
        return {k: rewrite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v) for v in value]
    return value


web = rewrite(load('web.environment.json'))
web.update(HOME='/var/lib/ikun', PATH='/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin',
           PROJECTS_PYTHON='/opt/ikun/venvs/projects/bin/python',
           PROJECTS_DB=str(target/'data/projects/projects.db'),
           IKUN_IPC_SOCKET='/run/ikun-production-projects/projects.sock',
           IKUN_PROJECTS_IPC_SOCKET='/run/ikun-production-projects/projects.sock',
           IKUN_AUTH_ORIGIN='https://ikun.ca', IKUN_AUTH_MAX_SESSIONS='1',
           IKUN_BUILD_SHA=web['IKUN_RELEASE_SHA'], IKUN_PROJECTS_BUILD_SHA=web['IKUN_RELEASE_SHA'])
token = secrets.token_urlsafe(48)
web.update(IKUN_IPC_TOKEN=token, IKUN_PROJECTS_IPC_TOKEN=token)
objects = {'web.environment.json': web,
           'hunter.live.environment.json': rewrite(load('hunter.live.environment.json')),
           'tracking.live.environment.json': rewrite(load('tracking.live.environment.json')),
           'tracking.live.json': rewrite(load('tracking.live.json')),
           # DeepSeek is opt-in. Field names, not set here: provider, model, base_url, timeout,
           # deepseek_api_key or api_key, fallback_provider, gemini_api_key, gemini_model.
           # The key may also be the DEEPSEEK_API_KEY environment variable.
           'ai.json': {'provider': 'codex', 'enabled': True, 'proxy': '', 'codex_bin': '/usr/local/bin/codex'},
           'tunnel.credentials.json': load('tunnel.credentials.json')}
for name, value in objects.items():
    path = stage/name
    path.write_text(json.dumps(value))
    path.chmod(0o600)
cloud = (source/'config/cloudflared.yml').read_text().replace(str(source), str(target))
assert 'protocol: http2' in cloud and 'hostname: ikun.ca' in cloud and 'hostname: v2.ikun.ca' in cloud
(stage/'cloudflared.yml').write_text(cloud)
(stage/'cloudflared.yml').chmod(0o600)
assert objects['hunter.live.environment.json']['HUNTER_EXTERNAL_IO_ENABLED'] == '1'
assert objects['hunter.live.environment.json']['HUNTER_REQUIRE_EXTERNAL_IO_DISABLED'] == '0'
assert objects['tracking.live.json']['remote_enabled'] is True
assert objects['hunter.live.environment.json']['HUNTER_API_TOKEN'] == web['HUNTER_API_TOKEN']
assert objects['tracking.live.environment.json']['TRACKING_API_TOKEN'] == web['TRACKING_API_TOKEN']
assert 'tampad_' not in objects['tracking.live.json'].get('adoptable_handles', [])
assert 'tampad_' in objects['tracking.live.json'].get('shared_watch_ids', {})
print('PRODUCTION_CONFIG_PREPARED_PRIVATE', stage)
