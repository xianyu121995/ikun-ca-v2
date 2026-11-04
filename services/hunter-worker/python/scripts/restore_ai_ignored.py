"""One-off repair for discoveries hidden by the old AI 忽略 path.

Prints what it would change. Writes only with --apply. Not imported by the
worker and not run at startup. Copy hunter.db before --apply.

Each argument is an X handle or a discovery id. A row is cleared (ignored=1
to ignored=0) only when it is currently ignored and no human review/ignore
audit is recorded for it. --include-human clears those too. Rating is left
as stored. Already-visible rows are printed and not rewritten.

Example:
  python scripts/restore_ai_ignored.py --db /path/hunter.db project_one dsc_...
  python scripts/restore_ai_ignored.py --db /path/hunter.db --apply project_one
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from hunterradar.migration import location


def lookup(db, token):
    text = token.strip().removeprefix('@')
    if text.startswith('dsc_'):
        return db.execute('SELECT * FROM discoveries WHERE discovery_id=?', (text,)).fetchone()
    return db.execute('SELECT * FROM discoveries WHERE target=?', (text.lower(),)).fetchone()


def human_ignore(db, row) -> bool:
    audits = db.execute(
        """SELECT action, detail FROM audit
           WHERE subject IN (?, ?) AND action IN ('discovery.research.patch', 'discovery.review')""",
        (row['discovery_id'], row['target'])).fetchall()
    for action, detail in audits:
        if action == 'discovery.review' or (detail and 'ignored' in detail):
            return True
    return False


def plan(db, handles, *, include_human=False):
    found = []
    for token in handles:
        row = lookup(db, token)
        if row is None:
            found.append({'input': token, 'action': 'missing'})
            continue
        human = human_ignore(db, row)
        ignored = int(row['ignored'])
        if ignored != 1:
            action = 'unchanged'
        elif human and not include_human:
            action = 'skipped_human'
        else:
            action = 'would_clear'
        found.append({
            'input': token,
            'discovery_id': row['discovery_id'],
            'handle': row['target'],
            'ignored': ignored,
            'rating': row['rating'],
            'rating_reason': row['rating_reason'] if 'rating_reason' in row.keys() else None,
            'human_ignore': human,
            'action': action,
        })
    return found


def run(path, handles, *, apply=False, include_human=False):
    database = location(Path(path), require_exists=True)
    db = sqlite3.connect(database, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA busy_timeout=5000')
        planned = plan(db, handles, include_human=include_human)
        if not apply or any(item['action'] == 'missing' for item in planned):
            if apply:
                for item in planned:
                    if item['action'] == 'would_clear':
                        item['action'] = 'not_applied'
            return planned
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        try:
            for item in planned:
                if item['action'] != 'would_clear':
                    continue
                changed = db.execute(
                    '''UPDATE discoveries SET ignored=0, version=version+1, updated_at=?
                       WHERE discovery_id=? AND ignored=1''',
                    (now, item['discovery_id'])).rowcount
                item['action'] = 'cleared' if changed else 'unchanged'
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return planned
    finally:
        db.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Clear AI-hidden discoveries by explicit handle. Dry-run unless --apply.')
    parser.add_argument('--db', required=True, type=Path, help='hunter.db to read; written only with --apply')
    parser.add_argument('--apply', action='store_true', help='set ignored=0 on the printed rows')
    parser.add_argument('--include-human', action='store_true', help='also clear rows with a human ignore/review audit')
    parser.add_argument('handles', nargs='+', help='X handle or discovery id')
    args = parser.parse_args(argv)
    try:
        rows = run(args.db, args.handles, apply=args.apply, include_human=args.include_human)
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    return 1 if any(row['action'] in ('missing', 'not_applied') for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
