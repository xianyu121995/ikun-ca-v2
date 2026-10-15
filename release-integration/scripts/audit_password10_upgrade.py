#!/usr/bin/env python3
"""Read-only live metadata checks and private online backups around the approved upgrade."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request
import re

ROOT = Path(__file__).resolve().parents[2]
TARGET = Path.home() / 'Library/Application Support/ikun-ca-v2-c0-lite'
DATA = TARGET / 'data'
OUTPUT = ROOT / 'release-integration/.runtime/c0-lite'


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def metadata():
    owner = json.loads((TARGET / 'owner.json').read_text())
    env = json.loads((TARGET / 'config/web.environment.json').read_text())
    assert env['DATA_ROOT'] == str(DATA) and env['IKUN_RELEASE_SHA'] == owner['candidate_sha']
    assert env['IKUN_AUTH_ORIGIN'] == 'https://v2.ikun.ca' and 'IKUN_AUTH_DEV' not in env
    result = {'candidate_sha': owner['candidate_sha'], 'data_root': str(DATA), 'databases': {}}
    release = TARGET / 'releases' / owner['candidate_sha']
    result['build_id'] = (release / 'apps/website/.next/BUILD_ID').read_text().strip()
    for domain in ('auth', 'projects'):
        path = DATA / domain / (domain + '.db')
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            item = {'path': str(path), 'inode': path.stat().st_ino, 'mode': oct(path.stat().st_mode & 0o777),
                    'schema_sha256': hashed(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()),
                    'integrity': 'ok', 'foreign_keys': 'ok'}
            if domain == 'auth':
                # Only aggregate fingerprints leave memory; no password hash or session token is emitted.
                item['users_sha256'] = hashed(db.execute('SELECT * FROM auth_users ORDER BY id').fetchall())
                item['users'] = db.execute('SELECT username,role,enabled,must_change_password FROM auth_users ORDER BY username').fetchall()
            result['databases'][domain] = item
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:' + env['PORT'] + '/health/ready', timeout=5) as response:
        result['health_status'] = response.status
        result['health'] = json.load(response)
    return result


def private_json(path, value):
    import os
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('before', 'after'))
    parser.add_argument('--receipt-prefix', default='password10')
    args = parser.parse_args()
    assert re.fullmatch('[a-z0-9-]{1,40}', args.receipt_prefix)
    prefix = args.receipt_prefix
    result = metadata()
    if args.phase == 'before':
        backup = TARGET / 'backups' / (prefix + '-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(mode=0o700, parents=True, exist_ok=False)
        for domain in ('auth', 'projects'):
            source = DATA / domain / (domain + '.db')
            destination = backup / (domain + '.db')
            destination.touch(mode=0o600, exist_ok=False)
            with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
                src.backup(dst)
                assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert not dst.execute('PRAGMA foreign_key_check').fetchall()
        result['backup'] = str(backup)
    else:
        before = json.loads((OUTPUT / (prefix + '-before.json')).read_text())
        assert result['data_root'] == before['data_root']
        for domain in ('auth', 'projects'):
            for key in ('path', 'inode', 'schema_sha256'):
                assert result['databases'][domain][key] == before['databases'][domain][key], (domain, key)
        assert result['databases']['auth']['users_sha256'] == before['databases']['auth']['users_sha256']
        result.update(data_paths_inodes_schema_unchanged=True, all_existing_user_rows_unchanged=True,
                      backup=before['backup'], previous_candidate=before['candidate_sha'])
    result['at'] = datetime.now(timezone.utc).isoformat()
    private_json(OUTPUT / (prefix + '-' + args.phase + '.json'), result)
    print(json.dumps({'phase': args.phase, 'status': 'PASS', 'candidate_sha': result['candidate_sha'],
                      'data_root': result['data_root'], 'build_id': result['build_id']}))


if __name__ == '__main__':
    main()
