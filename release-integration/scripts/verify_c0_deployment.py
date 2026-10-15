#!/usr/bin/env python3
"""Inspect and crash-recover only this owned, new, loopback C0-lite launchd job."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
TARGET = Path.home() / 'Library/Application Support/ikun-ca-v2-c0-lite'
LABEL = 'ca.ikun.v2.c0lite.web'


def main():
    receipt = json.loads((ROOT / 'release-integration/.runtime/c0-lite/deployment.json').read_text())
    owner = json.loads((TARGET / 'owner.json').read_text())
    assert receipt['runtime_root'] == str(TARGET) and receipt['web_label'] == LABEL
    assert owner['candidate_sha'] == receipt['candidate_sha']
    job = 'gui/' + str(os.getuid()) + '/' + LABEL
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = 'http://127.0.0.1:' + str(receipt['port'])

    def state():
        output = subprocess.check_output(['/bin/launchctl', 'print', job], text=True)
        match = re.search(r'^\s*pid = (\d+)$', output, re.M)
        return int(match.group(1)) if match else None

    def ready():
        try:
            with opener.open(url + '/health/ready', timeout=2) as response:
                return response.status == 200 and json.load(response)['data']['profile'] == 'c0-lite'
        except (OSError, ValueError):
            return False

    before = state()
    assert before and ready(), 'OWNED_WEB_NOT_READY'
    env = json.loads((TARGET / 'config/web.environment.json').read_text())
    assert env['NODE_ENV'] == 'production' and 'IKUN_AUTH_DEV' not in env
    process = subprocess.check_output(['/bin/ps', '-p', str(before), '-o', 'command='], text=True)
    assert str(TARGET) in process, 'PID_OWNERSHIP_MISMATCH'
    # KeepAlive recovery test, exact new job only. launchd owns its process group.
    subprocess.run(['/bin/launchctl', 'kill', 'SIGKILL', job], check=True)
    deadline = time.monotonic() + 55
    after = None
    while time.monotonic() < deadline:
        after = state()
        if after and after != before and ready():
            break
        time.sleep(.5)
    assert after and after != before and ready(), 'OWNED_KEEPALIVE_RECOVERY_FAILED'
    backup = TARGET / 'backups' / time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    database_checks = {}
    for domain in ('auth', 'projects'):
        source = TARGET / 'data' / domain / (domain + '.db')
        destination = backup / (domain + '.db')
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert dst.execute('PRAGMA foreign_key_check').fetchall() == []
            tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            counts = {name: dst.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in tables}
        destination.chmod(0o600)
        database_checks[domain] = {'source': str(source), 'backup': str(destination), 'integrity': 'ok',
                                   'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'row_counts': counts}
    # No monitor processes or production accounts are created by this check.
    report = {'status': 'PASS_LOCAL_ONLY', 'candidate_sha': receipt['candidate_sha'], 'before_pid': before, 'after_pid': after,
              'keepalive_recovered': True, 'origin': env['IKUN_AUTH_ORIGIN'], 'secure_cookie_dev_override': False,
              'health_ready': True, 'databases': database_checks,
              'processes': subprocess.check_output(['/bin/ps', '-axo', 'pid,ppid,rss,command'], text=True).splitlines(),
              'public_verified': False, 'workers_started': False}
    # Only owned process records, no environment/secrets or other process command lines.
    report['processes'] = [line for line in report['processes'] if str(TARGET) in line]
    out = ROOT / 'release-integration/.runtime/c0-lite/deployment-verification.json'
    out.write_text(json.dumps(report, indent=2) + '\n');out.chmod(0o600)
    print(json.dumps({'status': report['status'], 'receipt': str(out), 'keepalive_recovered': True}))


if __name__ == '__main__':
    main()
