"""Reuse accepted health checks; independent, verified server snapshots."""
import importlib.util
import os
import sys
from pathlib import Path

os.umask(0o077)
base = Path('/var/lib/ikun/production')
root = Path('/opt/ikun/current').resolve()
spec = importlib.util.spec_from_file_location('maintenance', root/'release-integration/scripts/v2_maintenance.py')
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)
if sys.argv[1] == 'health':
    errors = maintenance.health(root=base)
    # Approved Hunter REST-only release: no Watch synchronization is expected.
    # Keep all Tracking, provider, worker-heartbeat and delivery checks intact.
    import json, sqlite3
    config = json.loads((base/'config/hunter.live.environment.json').read_text())
    with sqlite3.connect((base/'data/hunter/hunter.db').as_uri()+'?mode=ro', uri=True) as db:
        policy = {k:json.loads(v) for k,v in db.execute("SELECT key,value FROM state WHERE key IN ('wss_state','watch_state')")}
    if (config.get('HUNTER_REST_ONLY') == '1' and not config.get('OPENNEWS_TOKEN')
            and policy.get('wss_state') == policy.get('watch_state') == 'disabled_rest_only'):
        retired = '猎手 Watch 同步异常（已持续 15 分钟以上）'
        errors = [e for e in errors if e != retired]
        since_path = base/'ops/health_since.json'
        since = json.loads(since_path.read_text()); since.pop(retired, None)
        maintenance.atomic(since_path, since)
        health_path = base/'ops/health.json'
        health = json.loads(health_path.read_text())
        health.update(healthy=not errors, errors=errors, hunter_transport='twitterapi_rest', tracking_transport='6551_wss')
        maintenance.atomic(health_path, health)
    print('PRODUCTION_HEALTH', '; '.join(errors) or 'OK')
elif sys.argv[1] == 'backup':
    sys.path.insert(0, '/opt/ikun/bin')
    from verified_backup import backup
    result = backup(base/'data', base/'backups/daily')
    # Publish complete weekly snapshots without removing any historical data.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import shutil
    day = datetime.now(ZoneInfo('Asia/Shanghai'))
    weekly = base/'backups/weekly'/day.strftime('%G-W%V')
    if day.weekday() == 0 and not weekly.exists():
        weekly.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = weekly.with_name('.partial-'+weekly.name)
        shutil.copytree(result, stage)
        stage.rename(weekly)
else:
    raise SystemExit('unsupported_operation')
