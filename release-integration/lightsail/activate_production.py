"""Approved handover only after proof that Mac jobs stopped and a verified final snapshot arrived."""
import json
import os
import pwd
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

assert os.getuid() == 0
base = Path('/var/lib/ikun/production')
source = Path(sys.argv[1]).resolve()
assert source.parent == Path('/home/ubuntu/ikun-cutover-private')
proof = json.loads((source/'mac-stopped.json').read_text())
assert set(proof['roles']) == {'web', 'hunter', 'tracking-live', 'tunnel', 'health', 'backup'}
assert proof['data_deleted'] is False
assert Path(proof['final_backup']).name == source.name
assert 0 <= time.time()-proof['stopped_at'] < 3600, 'stale_mac_handover'
manifest = json.loads((source/'verification.json').read_text())
assert set(manifest['databases']) == {'auth', 'projects', 'hunter', 'tracking'}
account = pwd.getpwnam('ikun')
sys.path.insert(0, '/opt/ikun/bin')
from verified_backup import counts

for role, expected in manifest['databases'].items():
    path = source/(role+'.db')
    assert path.stat().st_size == expected['bytes'] > 4096
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert counts(db) == expected['counts'], 'source_record_count_mismatch'
    assert not (base/'data'/role/(role+'.db')).exists(), 'production_database_already_exists'
print('SERVER_RECEIVED_FOUR_DATABASES_ALL_COUNTS_MATCH', flush=True)
# Only the isolated rehearsal jobs run at this point; close them to release loopback ports.
subprocess.run(['systemctl', 'stop', 'ikun-test-tunnel', 'ikun-web', 'ikun-projects'], check=True)
for role in manifest['databases']:
    folder = base/'data'/role
    folder.mkdir(mode=0o700)
    os.chown(folder, account.pw_uid, account.pw_gid)
    target = folder/(role+'.db')
    shutil.copyfile(source/(role+'.db'), target)
    target.chmod(0o600)
    os.chown(target, account.pw_uid, account.pw_gid)
(base/'ops/handover-verification.json').write_text(json.dumps(manifest, ensure_ascii=False))
os.chown(base/'ops/handover-verification.json', account.pw_uid, account.pw_gid)
config = json.loads((base/'config/web.environment.json').read_text())
assert config['IKUN_RELEASE_SHA'] == Path('/opt/ikun/current').resolve().name
assert config['IKUN_AUTH_ORIGIN'] == 'https://ikun.ca'


def start(unit):
    subprocess.run(['systemctl', 'enable', '--now', unit], check=True)
    print('SERVER_STARTED', unit, flush=True)


def ready(port, path='/health/ready'):
    for _ in range(60):
        try:
            req = urllib.request.Request('http://127.0.0.1:'+str(port)+path, headers={'Host': 'ikun.ca'})
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('server_not_ready:'+str(port))


start('ikun-projects.service')
start('ikun-web.service')
ready(4000)
approval = base/'ops/EXTERNAL_MONITORING_APPROVED'
approval.write_text(json.dumps({'mac_stopped_at': proof['stopped_at'], 'enabled_at': time.time()}))
approval.chmod(0o600)
os.chown(approval, account.pw_uid, account.pw_gid)
start('ikun-hunter.service')
ready(4011)
start('ikun-tracking-live.service')
ready(4012)
start('ikun-tunnel.service')
ready(65520, '/ready')
start('ikun-health.timer')
start('ikun-backup.timer')
subprocess.run(['systemctl', 'start', 'ikun-health.service', 'ikun-backup.service'], check=True)
print('PRODUCTION_HANDOVER_STARTED; SAME_TUNNEL_HTTP2; REHEARSAL_TUNNEL_STOPPED', flush=True)
