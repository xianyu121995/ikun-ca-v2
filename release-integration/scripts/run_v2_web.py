import json
import os
from pathlib import Path
root=Path(__file__).resolve().parents[2]
v2=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
p=v2/'config/web.environment.json'
if p.stat().st_mode & 0o077:raise SystemExit('private environment required')
env=json.loads(p.read_text())
if env.get('IKUN_TRACKING_INGEST_ENV_FILE'):env.pop('PROJECTS_INGEST_TRACKING_TOKEN',None)
node=v2/'toolchains/node24/bin/node'
env.update(HOME=str(Path.home()),PATH=str(node.parent)+':/opt/homebrew/bin:/usr/bin:/bin',LANG='en_US.UTF-8',TZ='Asia/Shanghai',NODE_ENV='production',NEXT_TELEMETRY_DISABLED='1',NODE_OPTIONS='--max-old-space-size=768')
os.chdir(root)
os.execve(str(node),[str(node),str(root/'scripts/start-c0-lite.mjs')],env)
