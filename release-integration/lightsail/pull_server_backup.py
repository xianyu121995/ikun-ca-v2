"""Mac daily pull: authenticated SSH/SCP, complete snapshots only, verify before publishing."""
import json
import logging
import logging.handlers
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

os.umask(0o077)
root = Path.home()/'Documents/ikun-ca-backups/lightsail'
root.mkdir(parents=True, exist_ok=True, mode=0o700)
log = logging.getLogger('backup-pull')
log.setLevel(logging.INFO)
log.addHandler(logging.handlers.RotatingFileHandler(root/'pull.log', maxBytes=1024*1024, backupCount=6))
options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3']


def once():
    result = subprocess.run(['/usr/bin/ssh', *options, 'ikun-server', 'sudo',
                             '/opt/ikun/venvs/projects/bin/python', '/opt/ikun/bin/export_backup.py'],
                            check=True, capture_output=True, text=True, timeout=60)
    info = json.loads(result.stdout)
    name = info['snapshot']
    assert re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9]{6}', name)
    assert info['path'] == '/home/ubuntu/ikun-backup-exports/'+name
    final = root/'daily'/name
    final.parent.mkdir(mode=0o700, exist_ok=True)
    if final.exists():
        log.info('already complete %s', name)
        print('MAC_BACKUP_ALREADY_PRESENT', name)
        return
    stage = final.with_name('.partial-'+name+'-'+str(os.getpid()))
    stage.mkdir(mode=0o700)
    for file in ('auth.db', 'hunter.db', 'tracking.db', 'projects.db', 'verification.json'):
        subprocess.run(['/usr/bin/scp', '-q', *options, 'ikun-server:'+info['path']+'/'+file, str(stage/file)],
                       check=True, capture_output=True, timeout=180)
        (stage/file).chmod(0o600)
    manifest = json.loads((stage/'verification.json').read_text())
    for role in ('auth', 'hunter', 'tracking', 'projects'):
        path = stage/(role+'.db')
        assert path.stat().st_size == manifest['databases'][role]['bytes'] > 4096
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            actual = {n: db.execute('SELECT count(*) FROM "'+n.replace('"','""')+'"').fetchone()[0]
                      for n in manifest['databases'][role]['counts']}
            assert actual == manifest['databases'][role]['counts']
    stage.rename(final)
    log.info('pulled and verified %s', name)
    print('MAC_BACKUP_PULLED_VERIFIED', final)


for attempt in range(4):
    try:
        once()
        break
    except Exception as exc:
        log.warning('attempt %d failed: %s', attempt+1, type(exc).__name__)
        if attempt == 3:
            raise SystemExit('SERVER_BACKUP_PULL_FAILED; see private pull.log')
        time.sleep(30*(attempt+1))
