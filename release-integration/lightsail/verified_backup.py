"""Four independent SQLite online snapshots, verified against each source transaction."""
import argparse
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROLES = {
    'auth': ('auth_users', 'auth_sessions'),
    'projects': ('projects',),
    'hunter': ('hunters', 'discoveries'),
    'tracking': ('projects', 'tweets', 'tweet_ledger'),
}


def counts(db):
    tables = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: db.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for name in tables}


def backup(root, destination):
    os.umask(0o077)
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S-%f')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = destination / ('.partial-' + stamp)
    stage.mkdir(mode=0o700)
    report = {'sqlite_version': sqlite3.sqlite_version, 'created_at': stamp, 'databases': {}}
    for role, required in ROLES.items():
        source = root / role / (role + '.db')
        assert source.is_file() and not source.is_symlink(), 'invalid_source:' + role
        assert source.stat().st_size > 4096, 'empty_source:' + role
        target = stage / (role + '.db')
        # A file: URI is mandatory. A bare filename ending ?mode=ro creates a different empty DB.
        with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=30) as src:
            src.execute('BEGIN')
            expected = counts(src)
            assert all(t in expected for t in required), 'missing_source_tables:' + role
            deadline = time.monotonic() + 120

            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise TimeoutError('backup_timeout:' + role)

            with sqlite3.connect(target) as dst:
                src.backup(dst, pages=256, sleep=.05, progress=progress)
                assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'integrity:' + role
                assert not dst.execute('PRAGMA foreign_key_check').fetchall(), 'foreign_keys:' + role
                actual = counts(dst)
                assert actual == expected, 'record_count_mismatch:' + role
            src.rollback()
        target.chmod(0o600)
        assert target.stat().st_size > 4096, 'empty_backup:' + role
        report['databases'][role] = {'bytes': target.stat().st_size, 'integrity': 'ok',
                                     'all_table_counts_match': True, 'counts': actual}
    (stage / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    final = destination / stamp
    stage.rename(final)
    print('VERIFIED_BACKUP', final, flush=True)
    for role, item in report['databases'].items():
        print(role, item['bytes'], 'integrity=ok all_table_counts_match=true',
              {k: item['counts'][k] for k in ROLES[role]}, flush=True)
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    backup(args.root, args.destination)
