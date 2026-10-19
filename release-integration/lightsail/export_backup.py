"""Export only a completed production snapshot to the authenticated SSH user's private directory."""
import json
import os
import pwd
import shutil
from pathlib import Path

assert os.getuid() == 0
account = pwd.getpwnam('ubuntu')
daily = Path('/var/lib/ikun/production/backups/daily')
complete = sorted(p for p in daily.iterdir()
                  if p.is_dir() and not p.name.startswith('.') and (p/'verification.json').is_file())
assert complete, 'no_complete_backup'
source = complete[-1]
manifest = json.loads((source/'verification.json').read_text())
assert set(manifest['databases']) == {'auth', 'hunter', 'tracking', 'projects'}
dest = Path('/home/ubuntu/ikun-backup-exports')/source.name
dest.parent.mkdir(mode=0o700, exist_ok=True)
os.chown(dest.parent, account.pw_uid, account.pw_gid)
if not dest.exists():
    stage = dest.with_name('.partial-'+dest.name+'-'+str(os.getpid()))
    stage.mkdir(mode=0o700)
    for name in ('auth.db', 'hunter.db', 'tracking.db', 'projects.db', 'verification.json'):
        target = stage/name
        shutil.copyfile(source/name, target)
        target.chmod(0o600)
        os.chown(target, account.pw_uid, account.pw_gid)
    os.chown(stage, account.pw_uid, account.pw_gid)
    stage.rename(dest)
print(json.dumps({'snapshot': source.name, 'path': str(dest)}))
