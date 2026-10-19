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
