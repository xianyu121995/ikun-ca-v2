#!/usr/bin/env python3
"""One-off: fill projects.discovered_at (NULL only) from Hunter's first_discovered_at.

Usage: backfill_discovered_at.py [--apply]   (dry run by default; back up first)
Matches project_sources(source='hunter') external ids to Hunter target identities
(entity_key or 'x-user:'+x_user_id). Never overwrites an existing value.
"""
import argparse, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / 'Library/Application Support/ikun-ca-v2-c0-lite'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); ap.add_argument('--root', default=str(ROOT))
    a = ap.parse_args(); root = Path(a.root)
    hunter = sqlite3.connect('file:' + str(root / 'data/hunter/hunter.db') + '?mode=ro', uri=True)
    projects = sqlite3.connect(str(root / 'data/projects/projects.db'))
    todo = projects.execute("SELECT id,name FROM projects WHERE discovered_at IS NULL").fetchall()
    found = {}
    for pid, name in todo:
        best = None
        for (ext,) in projects.execute("SELECT external_id FROM project_sources WHERE project_id=? AND source='hunter'", (pid,)):
            row = hunter.execute("SELECT min(d.first_discovered_at) FROM target_identities i JOIN discoveries d ON d.target=i.anchor "
                                 "WHERE i.entity_key=? OR ('x-user:'||i.x_user_id)=?", (ext, ext)).fetchone()
            if row and row[0]: best = row[0] if best is None else min(best, row[0])
        if best: found[pid] = (name, datetime.fromtimestamp(best, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
    for pid, (name, value) in found.items(): print(value, name)
    print(f'{len(found)}/{len(todo)} matched' + ('' if a.apply else ' (dry run)'))
    if a.apply:
        with projects:
            for pid, (_, value) in found.items():
                projects.execute("UPDATE projects SET discovered_at=? WHERE id=? AND discovered_at IS NULL", (value, pid))
        print('applied')

if __name__ == '__main__': main()
