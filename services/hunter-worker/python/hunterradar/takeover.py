"""Offline, whitelist-only legacy Hunter import. Never imports a network adapter.

The caller supplies reviewed immutable snapshots/proofs; this is not an authority
to stop services, establish ownership, or turn on an external source.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

from .migration import inspect, location, metadata
from .parsers import Target, handle
from .retention import TTL_US, WINDOW_US, advance, micros, watermark
from .store import Conflict, Store, LEGACY_DIRECTORY_PREFIX

PROTOCOL = 'hunter-takeover-package-v1'
PROTOCOL_V2 = 'hunter-takeover-package-v2'
NO_PROJECT_MAP = 'not-applicable:directory-v2'
EXECUTION = 'IKUN-ONLY-2026-10-16'
MAX_BYTES = 64 * 1024 * 1024
FIELDS = {
    'hunters': ('username', 'user_id', 'display_name', 'active', 'created_at', 'followers', 'monitor_mode', 'profile_status'),
    'twitterapi_following_snapshots': ('hunter_username', 'target_id', 'target_username', 'target_name', 'first_seen_at', 'last_seen_at'),
    'twitterapi_poll_state': ('hunter_username', 'baseline_ready', 'last_success_at'),
    'alerts': ('target_key', 'target_id', 'target_username', 'triggered_at'),
    'follows': ('id', 'event_key', 'hunter_username', 'hunter_id', 'target_id', 'target_username', 'target_name', 'followed_at', 'received_at', 'event_type', 'source'),
    'raw_payloads': ('id',),
    'metadata': ('key',),
}
# v1 keeps its original whitelist/hash. Added v2 times are private audit only.
FIELDS_V2 = dict(FIELDS, hunters=(*FIELDS['hunters'], 'profile_scanned_at'),
                 twitterapi_poll_state=(*FIELDS['twitterapi_poll_state'], 'last_started_at', 'next_poll_after'))
KEYS = {'hunters': 'username', 'twitterapi_poll_state': 'hunter_username', 'alerts': 'target_key',
        'follows': 'id', 'raw_payloads': 'id', 'metadata': 'key'}
OUTCOMES = ('imported', 'deduplicated', 'quarantined', 'excluded')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('invalid_sha256')
    return value


def private_file(value):
    path = Path(value).absolute()
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('symlinked_input_path')
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or entry.st_mode & 0o077:
        raise ValueError('input_must_be_private_regular_file')
    if path.parent.stat().st_mode & 0o077:
        raise ValueError('input_directory_must_be_private')
    return path


def read_private(value, expected):
    path = private_file(value)
    sha(expected)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('input_too_large')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('input_sha256_mismatch')
    return data


def unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate_json_key')
        output[key] = value
    return output


def read_json(value, expected):
    return json.loads(read_private(value, expected), object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid_json_number')))


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError('unsupported_input_fields')


def stable(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9]{1,40}', value):
        raise ValueError('missing_or_invalid_stable_id')
    return value


def instant(value):
    if not isinstance(value, str):
        raise ValueError('invalid_original_time')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        stamp = parsed.timestamp()
        if not math.isfinite(stamp) or stamp < 0:
            raise ValueError()
        # Avoid loss of the microsecond TTL boundary through float arithmetic.
        return micros(str(int(stamp)) + '.' + f'{parsed.microsecond:06d}')
    except (ValueError, OverflowError, OSError):
        raise ValueError('invalid_original_time') from None


def text(value, maximum):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError('invalid_legacy_text')
    return value


def baseline_digest(rows):
    return digest(sorted(rows, key=canonical))


def proofs(ownership, projects, source_sha256):
    exact(ownership, ('protocol', 'execution_id', 'source_sha256', 'captured_at', 'source_stopped',
                      'final_watermark_at', 'hunters', 'discoveries', 'baselines'))
    if (ownership['protocol'] != 'hunter-takeover-ownership-v1' or ownership['execution_id'] != EXECUTION
            or ownership['source_sha256'] != source_sha256 or type(ownership['source_stopped']) is not bool):
        raise ValueError('ownership_binding_mismatch')
    captured = instant(ownership['captured_at'])
    final = ownership['final_watermark_at']
    if ownership['source_stopped']:
        if final is None or instant(final) > captured:
            raise ValueError('final_watermark_required')
    elif final is not None:
        raise ValueError('live_source_has_no_final_watermark')
    groups = []
    for field in ('hunters', 'discoveries', 'baselines'):
        if not isinstance(ownership[field], list) or len(ownership[field]) > 100000:
            raise ValueError('invalid_ownership_rows')
        group = {}
        for row in ownership[field]:
            if field == 'baselines':
                exact(row, ('x_user_id', 'complete', 'snapshot_count', 'snapshot_sha256', 'last_success_at', 'evidence_sha256'))
                if type(row['complete']) is not bool or type(row['snapshot_count']) is not int or row['snapshot_count'] < 0:
                    raise ValueError('invalid_baseline_proof')
                sha(row['snapshot_sha256']); instant(row['last_success_at'])
            else:
                exact(row, ('x_user_id', 'ownership', 'evidence_sha256'))
                if row['ownership'] not in ('ikun', 'alpha', 'unknown'):
                    raise ValueError('invalid_ownership')
            identifier = stable(row['x_user_id']); sha(row['evidence_sha256'])
            if identifier in group:
                raise ValueError('ambiguous_ownership')
            group[identifier] = row
        groups.append(group)
    exact(projects, ('protocol', 'execution_id', 'items'))
    if projects['protocol'] != 'hunter-takeover-project-map-v1' or projects['execution_id'] != EXECUTION or not isinstance(projects['items'], list):
        raise ValueError('projects_mapping_binding_mismatch')
    refs = {}
    for row in projects['items']:
        exact(row, ('x_user_id', 'project_id', 'source_hash'))
        identifier = stable(row['x_user_id']); sha(row['source_hash'])
        try:
            project = uuid.UUID(row['project_id'].removeprefix('prj_'))
            if project.version != 4 or row['project_id'] != 'prj_' + str(project):
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise ValueError('invalid_canonical_project_id') from None
        if identifier in refs:
            raise ValueError('ambiguous_projects_mapping')
        refs[identifier] = row['project_id']
    return *groups, refs, captured


def write_package(path, package):
    path = Path(path).absolute()
    # Do not create directories or replace an operator's reviewed package.
    if not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        raise ValueError('output_directory_must_be_private')
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('symlinked_output_path')
    data = (canonical(package) + '\n').encode()
    if len(data) > MAX_BYTES:
        raise ValueError('package_too_large')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    parent_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return hashlib.sha256(data).hexdigest()


def prepare(source, source_sha256, ownership_path, ownership_sha256, projects_path, projects_sha256, output):
    source = private_file(source)
    read_private(source, source_sha256)
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(source) + suffix).exists():
            raise ValueError('source_must_be_sealed_snapshot_without_sidecars')
    ownership = read_json(ownership_path, ownership_sha256)
    projects = read_json(projects_path, projects_sha256)
    proofs(ownership, projects, source_sha256)
    rows = {}
    with sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('legacy_snapshot_integrity_failed')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(FIELDS):
            raise ValueError('unreviewed_legacy_tables')
        for table, fields in FIELDS.items():
            if not set(fields) <= {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}:
                raise ValueError('legacy_fields_missing')
            rows[table] = [dict(row) for row in db.execute('SELECT ' + ','.join(fields) + ' FROM ' + table)]
    # Detect accidental input mutation while exporting. No online source is accepted.
    read_private(source, source_sha256)
    package = dict(protocol=PROTOCOL, execution_id=EXECUTION, source_sha256=source_sha256,
                   ownership_sha256=ownership_sha256, projects_sha256=projects_sha256,
                   ownership=ownership, projects=projects, rows=rows)
    validate(package)
    return {'package_sha256': write_package(output, package), 'input': {k: len(v) for k, v in rows.items()},
            'source_stopped': ownership['source_stopped'], 'network_requests': 0, 'watch_writes': 0}


def validate(package):
    exact(package, ('protocol', 'execution_id', 'source_sha256', 'ownership_sha256', 'projects_sha256', 'ownership', 'projects', 'rows'))
    if package['protocol'] != PROTOCOL or package['execution_id'] != EXECUTION:
        raise ValueError('unsupported_takeover_protocol')
    for field in ('source_sha256', 'ownership_sha256', 'projects_sha256'):
        sha(package[field])
    # File hashes authenticate the operator's inputs in prepare; the package hash
    # seals this projection, including proofs. They are not signatures.
    result = proofs(package['ownership'], package['projects'], package['source_sha256'])
    exact(package['rows'], FIELDS)
    for table, rows in package['rows'].items():
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError('invalid_import_rows')
        seen = set()
        for row in rows:
            exact(row, FIELDS[table])
            key = row_key(table, row)
            if key in seen:
                raise ValueError('duplicate_source_primary_key')
            seen.add(key)
    return result


def row_key(table, row):
    if table == 'twitterapi_following_snapshots':
        value = [row['hunter_username'], row['target_id']]
    else:
        value = row[KEYS[table]]
    # SQLite's legacy NOCASE primary keys are case insensitive.
    if table in ('hunters', 'twitterapi_poll_state') and isinstance(value, str):
        value = value.lower()
    if table == 'twitterapi_following_snapshots' and isinstance(value[0], str):
        value[0] = value[0].lower()
    return digest(value)


class Decision(Exception):
    def __init__(self, outcome, reason):
        self.outcome, self.reason = outcome, reason


def require_owned(identifier, group):
    proof = group.get(identifier)
    owner = proof['ownership'] if proof else 'unknown'
    if owner == 'alpha':
        raise Decision('excluded', 'ALPHA_EXCLUDED')
    if owner != 'ikun':
        raise Decision('quarantined', 'OWNERSHIP_UNKNOWN')


def require_takeover_schema(db):
    if max(metadata(db)[0])!=5:
        raise ValueError('explicit_hunter_schema5_migration_required')


class Importer:
    def __init__(self, store, db, package, package_sha256, clock):
        self.store, self.db, self.package, self.package_sha256, self.clock = store, db, package, package_sha256, clock
        self.owners, self.discovery_owners, self.baseline_proofs, self.projects, self.captured = validate(package)
        self.source_cutoff = (instant(package['ownership']['final_watermark_at'])
                              if package['ownership']['source_stopped'] else self.captured)
        self.hunters = {}
        self.imported_hunters = set()
        self.snapshots = defaultdict(list)
        self.good_snapshots = Counter()
        self.bad_snapshots = set()
        self.inserted = Counter()
        self.profiles = {}
        self.created_discoveries = set()
        self.tables = {table: Counter(input=len(rows)) for table, rows in package['rows'].items()}
        self.reasons = Counter()
        self.legacy_hunters = {}
        self.stable_hunters = Counter()
        for row in package['rows']['hunters']:
            try:
                self.legacy_hunters[handle(row['username'])] = row
                self.stable_hunters[stable(row['user_id'])] += 1
            except ValueError:
                pass
        for row in package['rows']['twitterapi_following_snapshots']:
            try:
                self.snapshots[handle(row['hunter_username'])].append(row)
            except ValueError:
                pass

    def count_insert(self, table):
        self.inserted[table] += 1

    def run_row(self, table, row, operation):
        key, row_hash = row_key(table, row), digest(row)
        previous = self.db.execute('SELECT * FROM hunter_takeover_rows WHERE source_system=? AND source_table=? AND source_key_sha256=?',
                                   ('legacy-hunter', table, key)).fetchone()
        if previous:
            if previous['row_sha256'] != row_hash:
                outcome, reason, ref = 'quarantined', 'SOURCE_ROW_HASH_CONFLICT', None
            else:
                outcome, reason, ref = 'deduplicated', 'SOURCE_ROW_ALREADY_RECORDED', previous['target_ref']
                if table == 'hunters' and ref:
                    owner = self.owners.get(row['user_id'], {}).get('ownership', 'unknown')
                    if owner != 'ikun':
                        outcome, reason = 'quarantined', 'OWNERSHIP_CHANGED_REVIEW_REQUIRED'
                    else:
                        existing = self.db.execute('SELECT * FROM hunters WHERE id=?', (ref,)).fetchone()
                        if existing:
                            self.hunters[handle(row['username'])] = dict(existing)
                elif table == 'alerts' and ref and self.discovery_owners.get(row['target_id'], {}).get('ownership') != 'ikun':
                    outcome, reason = 'quarantined', 'OWNERSHIP_CHANGED_REVIEW_REQUIRED'
            if outcome == 'quarantined':
                self.db.execute('INSERT INTO hunter_takeover_conflicts(package_sha256,source_table,source_key_sha256,row_sha256,prior_row_sha256,reason) VALUES(?,?,?,?,?,?)',
                                (self.package_sha256, table, key, row_hash, previous['row_sha256'], reason))
            self.record_count(table, outcome, reason)
            return
        inserted_before = self.inserted.copy()
        self.db.execute('SAVEPOINT import_row')
        try:
            outcome, reason, ref = operation(row)
            self.db.execute('RELEASE import_row')
        except (Decision, ValueError, Conflict, sqlite3.IntegrityError) as error:
            self.db.execute('ROLLBACK TO import_row'); self.db.execute('RELEASE import_row')
            self.inserted = inserted_before
            if isinstance(error, Decision):
                outcome, reason = error.outcome, error.reason
            else:
                outcome, reason = 'quarantined', ('IDENTITY_OR_CONSTRAINT_CONFLICT' if isinstance(error, (Conflict, sqlite3.IntegrityError))
                                                   else 'INVALID_LEGACY_VALUE')
            ref = None
            if table == 'twitterapi_following_snapshots':
                try:
                    self.bad_snapshots.add(handle(row['hunter_username']))
                except ValueError:
                    pass
        self.db.execute('INSERT INTO hunter_takeover_rows(source_system,source_table,source_key_sha256,row_sha256,outcome,reason,target_ref,package_sha256) VALUES(?,?,?,?,?,?,?,?)',
                        ('legacy-hunter', table, key, row_hash, outcome, reason, ref, self.package_sha256))
        self.record_count(table, outcome, reason)

    def record_count(self, table, outcome, reason):
        self.tables[table][outcome] += 1
        self.reasons[reason] += 1

    def hunter(self, row):
        identifier = stable(row['user_id']); require_owned(identifier, self.owners)
        if self.stable_hunters[identifier] != 1:
            raise Decision('quarantined', 'AMBIGUOUS_SOURCE_HUNTER_ID')
        username = handle(row['username']); created = instant(row['created_at'])
        if created > self.source_cutoff or type(row['active']) is not int or row['active'] not in (0, 1):
            raise ValueError('invalid_hunter_state')
        if type(row['followers']) is not int or row['followers'] < 0:
            raise ValueError('invalid_follower_count')
        mode = 'WSS' if row['followers'] >= 5000 else 'REST'
        if row['monitor_mode'] != mode:
            raise Decision('quarantined', 'FOLLOWER_MODE_CONFLICT')
        if row['profile_status'] != 'READY':
            raise Decision('quarantined', 'LEGACY_PROFILE_NOT_READY')
        existing = self.db.execute('SELECT * FROM hunters WHERE user_id=?', (identifier,)).fetchone()
        alias = self.db.execute('SELECT * FROM hunters WHERE username=?', (username,)).fetchone()
        if alias and (not existing or alias['id'] != existing['id']):
            raise Decision('quarantined', 'HUNTER_ALIAS_CONFLICT')
        if existing:
            self.hunters[username] = dict(existing)
            return 'deduplicated', 'EXISTING_V2_HUNTER_PRESERVED', existing['id']
        local_id = str(uuid.uuid4())
        self.db.execute('''INSERT INTO hunters(id,username,user_id,name,enabled,created_at,active_since,followers,mode,
            profile_status,next_profile_at,watch_covered,baseline_ready) VALUES(?,?,?,?,?,?,?,?,?,'ready',?,0,0)''',
                        (local_id, username, identifier, text(row['display_name'], 200), row['active'], created / 1e6,
                         created / 1e6, row['followers'], mode, self.clock / 1e6))
        current = dict(self.db.execute('SELECT * FROM hunters WHERE id=?', (local_id,)).fetchone())
        self.hunters[username] = current; self.imported_hunters.add(local_id); self.count_insert('hunters')
        return 'imported', 'HUNTER_IMPORTED_OFFLINE', local_id

    def mapped_hunter(self, username):
        username = handle(username)
        legacy = self.legacy_hunters.get(username)
        if legacy:
            require_owned(stable(legacy['user_id']), self.owners)
        current = self.hunters.get(username)
        if not current:
            raise Decision('quarantined', 'HUNTER_MAPPING_UNAVAILABLE')
        require_owned(current['user_id'], self.owners)
        if current['id'] not in self.imported_hunters:
            raise Decision('excluded', 'EXISTING_V2_GENERATION_PRESERVED')
        return current

    def identity(self, row, at):
        identifier = stable(row['target_id']); username = handle(row['target_username'])
        before = self.db.execute('SELECT * FROM target_identities WHERE x_user_id=?', (identifier,)).fetchone()
        alias = self.db.execute('SELECT i.* FROM target_identities i JOIN target_aliases a USING(entity_key) WHERE a.x_handle=?', (username,)).fetchone()
        if alias and (alias['x_user_id'] != identifier or (before and alias['entity_key'] != before['entity_key'])):
            raise Conflict('legacy_target_alias_conflict')
        if before:
            # Importing an old alias never edits a v2 identity or its current handle.
            return before['anchor']
        anchor = self.store.resolve_target(self.db, Target(username, identifier), at / 1e6)
        self.count_insert('target_identities'); self.count_insert('target_aliases')
        return anchor

    def snapshot(self, row):
        current = self.mapped_hunter(row['hunter_username'])
        first, last = instant(row['first_seen_at']), instant(row['last_seen_at'])
        if first > last or last > self.source_cutoff:
            raise ValueError('invalid_snapshot_times')
        anchor = self.identity(row, last)
        inserted = self.db.execute('INSERT OR IGNORE INTO seen_targets(hunter_id,generation,target,user_id) VALUES(?,?,?,?)',
                                   (current['id'], current['generation'], anchor, row['target_id'])).rowcount
        if inserted:
            self.count_insert('seen_targets')
        self.db.execute('INSERT OR IGNORE INTO hunter_takeover_seen_times(hunter_id,generation,target,x_user_id,first_seen_at_us,last_seen_at_us) VALUES(?,?,?,?,?,?)',
                        (current['id'], current['generation'], anchor, row['target_id'], first, last))
        name = text(row['target_name'], 200)
        if name and (row['target_id'] not in self.profiles or self.profiles[row['target_id']][0] < last):
            self.profiles[row['target_id']] = (last, name)
        self.good_snapshots[current['id']] += 1
        return ('imported' if inserted else 'deduplicated'), 'BASELINE_NO_EVENT', current['id']

    def poll(self, row):
        current = self.mapped_hunter(row['hunter_username'])
        if type(row['baseline_ready']) is not int or row['baseline_ready'] not in (0, 1):
            raise ValueError('invalid_baseline_state')
        success = instant(row['last_success_at']) if row['last_success_at'] is not None else None
        if success is not None and success > self.source_cutoff:
            raise ValueError('future_poll_success')
        snapshots = self.snapshots[current['username']]
        fingerprint = baseline_digest(snapshots)
        proof = self.baseline_proofs.get(current['user_id'])
        proven = bool(self.package['ownership']['source_stopped'] and current['mode'] == 'REST'
                      and current['enabled'] and row['baseline_ready'] == 1 and success is not None
                      and proof and proof['complete'] and proof['snapshot_count'] == len(snapshots)
                      and proof['snapshot_sha256'] == fingerprint
                      and instant(proof['last_success_at']) == success
                      and current['username'] not in self.bad_snapshots
                      and self.good_snapshots[current['id']] == len(snapshots)
                      and all(instant(s['last_seen_at']) <= success for s in snapshots))
        first = min((instant(r['first_seen_at']) for r in snapshots), default=None)
        last = max((instant(r['last_seen_at']) for r in snapshots), default=None)
        self.db.execute('INSERT INTO hunter_takeover_baselines(hunter_id,source_sha256,snapshot_sha256,snapshot_count,first_seen_at_us,last_seen_at_us,last_success_at_us,ready_proven) VALUES(?,?,?,?,?,?,?,?)',
                        (current['id'], self.package['source_sha256'], fingerprint, len(snapshots), first, last, success, int(proven)))
        if proven:
            self.db.execute('UPDATE hunters SET baseline_ready=1,baseline_at=?,last_poll_at=?,next_poll_at=? WHERE id=?',
                            (success / 1e6, success / 1e6, max(self.clock, success + 3600_000000) / 1e6, current['id']))
        return 'imported', ('REST_BASELINE_PROVEN' if proven else 'BASELINE_STAGED_NOT_READY'), current['id']

    def alert(self, row):
        if row['target_id'] is None or row['target_id'] == '':
            raise Decision('quarantined', 'MISSING_STABLE_TARGET_ID')
        identifier = stable(row['target_id']); require_owned(identifier, self.discovery_owners)
        first = instant(row['triggered_at'])
        if first > self.source_cutoff:
            raise ValueError('future_discovery_time')
        old = self.db.execute('SELECT * FROM target_discovery_ledger WHERE x_user_id=?', (identifier,)).fetchone()
        if old:
            return 'deduplicated', 'EXISTING_DISCOVERY_FENCE_PRESERVED', old['discovery_id']
        discovery_id = 'dsc_' + str(uuid.uuid4())
        expired = first + TTL_US <= self.clock
        self.db.execute('INSERT INTO target_discovery_ledger(scope,platform,x_user_id,discovery_id,first_discovered_at_us,retired_at_us) VALUES(?,?,?,?,?,?)',
                        ('ikun-main', 'x', identifier, discovery_id, first, self.clock if expired else None))
        self.count_insert('target_discovery_ledger')
        if identifier in self.projects:
            project = self.projects[identifier]
            previous = self.db.execute('SELECT project_id FROM hunter_takeover_project_refs WHERE x_user_id=?', (identifier,)).fetchone()
            if previous and previous[0] != project:
                raise Decision('quarantined', 'CANONICAL_MAPPING_CONFLICT')
            self.db.execute('INSERT OR IGNORE INTO hunter_takeover_project_refs(x_user_id,project_id,map_sha256) VALUES(?,?,?)',
                            (identifier, project, self.package['projects_sha256']))
        if expired:
            return 'imported', 'EXPIRED_DISCOVERY_LEDGER_ONLY', discovery_id
        # A missing/reused handle must never prevent the stable discovered fence.
        self.db.execute('SAVEPOINT discovery_body')
        inserted_before = self.inserted.copy()
        try:
            anchor = self.identity(row, first)
            if self.db.execute('SELECT 1 FROM discoveries WHERE target=?', (anchor,)).fetchone():
                raise Conflict('existing_discovery_body')
            self.db.execute('''INSERT INTO discoveries(target,first_discovered_at,discovery_id,updated_at,first_discovered_at_us,profile_json)
                VALUES(?,?,?,?,?,?)''', (anchor, first / 1e6, discovery_id, first / 1e6, first,
                                         canonical({'target_name': self.profiles.get(identifier, (0, ''))[1], 'description': ''})))
            self.db.execute('RELEASE discovery_body'); self.count_insert('discoveries')
            self.created_discoveries.add(discovery_id)
            return 'imported', 'DISCOVERY_IMPORTED_NO_PUBLICATION', discovery_id
        except (ValueError, Conflict, sqlite3.IntegrityError):
            self.db.execute('ROLLBACK TO discovery_body'); self.db.execute('RELEASE discovery_body')
            self.inserted = inserted_before
            return 'imported', 'DISCOVERY_BODY_QUARANTINED_LEDGER_SAVED', discovery_id

    def follow(self, row):
        current = self.mapped_hunter(row['hunter_username'])
        if stable(row['hunter_id']) != current['user_id']:
            raise Decision('quarantined', 'FOLLOW_DIRECTION_ID_CONFLICT')
        target_id = stable(row['target_id'])
        occurred, received = instant(row['followed_at']), instant(row['received_at'])
        if occurred > received or received > self.source_cutoff:
            raise ValueError('invalid_follow_times')
        if occurred < self.clock - WINDOW_US:
            raise Decision('excluded', 'OUTSIDE_ORIGINAL_72H')
        if occurred < micros(current['created_at']):
            raise Decision('quarantined', 'FOLLOW_BEFORE_HUNTER_CREATED')
        if row['event_type'] != 'NEW_FOLLOWER' or row['source'] not in ('6551_WSS', 'TWITTERAPI_IO'):
            raise Decision('quarantined', 'FOLLOW_DIRECTION_OR_SOURCE_UNKNOWN')
        if row['source'] != ('6551_WSS' if current['mode'] == 'WSS' else 'TWITTERAPI_IO'):
            raise Decision('quarantined', 'FOLLOW_CHANNEL_CONFLICT')
        if target_id == current['user_id'] or handle(row['target_username']) == current['username']:
            raise Decision('excluded', 'SELF_FOLLOW_EXCLUDED')
        ledger = self.db.execute('SELECT * FROM target_discovery_ledger WHERE x_user_id=?', (target_id,)).fetchone()
        if ledger and (ledger['retired_at_us'] is not None or ledger['first_discovered_at_us'] + TTL_US <= self.clock):
            raise Decision('excluded', 'TARGET_ALREADY_RETIRED')
        if ledger and not self.db.execute('SELECT 1 FROM discoveries WHERE discovery_id=?', (ledger['discovery_id'],)).fetchone():
            raise Decision('quarantined', 'DISCOVERY_BODY_REQUIRES_REVIEW')
        anchor = self.identity(row, occurred)
        original_key = text(row['event_key'], 512)
        if not original_key:
            raise ValueError('missing_event_key')
        event_key = digest(['legacy-hunter-v1', original_key])
        keyed = self.db.execute('SELECT * FROM follow_events WHERE event_key=?', (event_key,)).fetchone()
        if keyed and (keyed['hunter_x_id'] != current['user_id'] or keyed['target_id'] != target_id
                      or keyed['occurred_at'] != occurred / 1e6 or keyed['received_at'] != received / 1e6
                      or keyed['source'] != row['source'] or keyed['target_name'] != text(row['target_name'], 200)):
            raise Decision('quarantined', 'EVENT_KEY_HASH_CONFLICT')
        existing = keyed or self.db.execute('''SELECT 1 FROM follow_events WHERE
            hunter_x_id=? AND target_id=? AND occurred_at=? AND source=?''',
                                            (current['user_id'], target_id, occurred / 1e6, row['source'])).fetchone()
        if existing:
            return 'deduplicated', 'FOLLOW_EVENT_ALREADY_SEEN', event_key
        self.db.execute('''INSERT INTO follow_events(event_key,hunter_id,hunter_x_id,generation,target,target_id,
            target_name,description,occurred_at,received_at,window_at,source,time_basis) VALUES(?,?,?,?,?,?,?,'',?,?,?,?,?)''',
                        (event_key, current['id'], current['user_id'], current['generation'], anchor, target_id,
                         text(row['target_name'], 200), occurred / 1e6, received / 1e6, occurred / 1e6,
                         row['source'], 'legacy_provider_event' if row['source'] == '6551_WSS' else 'first_observed_after_baseline'))
        if ledger and ledger['discovery_id'] in self.created_discoveries and text(row['target_name'], 200):
            # Only a body created in this same offline transaction can be filled.
            # Existing human fields/revision and the first discovery time never change.
            profile = self.db.execute('SELECT profile_json FROM discoveries WHERE discovery_id=?', (ledger['discovery_id'],)).fetchone()
            if profile and not json.loads(profile[0]).get('target_name'):
                self.db.execute('UPDATE discoveries SET profile_json=? WHERE discovery_id=?',
                                (canonical({'target_name': row['target_name'], 'description': ''}), ledger['discovery_id']))
        self.count_insert('follow_events')
        return 'imported', 'FOLLOW_IMPORTED_NO_AGGREGATION', event_key

    def execute(self, progress):
        operations = {'hunters': self.hunter, 'twitterapi_following_snapshots': self.snapshot,
                      'twitterapi_poll_state': self.poll, 'alerts': self.alert, 'follows': self.follow,
                      'raw_payloads': lambda _: ('excluded', 'RAW_PAYLOAD_EXCLUDED', None),
                      'metadata': lambda _: ('excluded', 'METADATA_VALUE_EXCLUDED', None)}
        for table, operation in operations.items():
            rows = self.package['rows'][table]
            if table == 'alerts':
                def sort_alert(row):
                    try:
                        return instant(row['triggered_at']), row_key(table, row)
                    except ValueError:
                        return 2**63, row_key(table, row)
                rows = sorted(rows, key=sort_alert)
            for row in rows:
                self.run_row(table, row, operation)
            if progress:
                progress(table)
        tables = {table: {key: counts[key] for key in ('input', *OUTCOMES)} for table, counts in self.tables.items()}
        if any(r['input'] != sum(r[key] for key in OUTCOMES) for r in tables.values()):
            raise ValueError('import_count_reconciliation_failed')
        return dict(protocol=PROTOCOL, execution_id=EXECUTION, package_sha256=self.package_sha256,
                    effective_at_us=self.clock, source_stopped=self.package['ownership']['source_stopped'],
                    tables=tables, reasons=dict(sorted(self.reasons.items())), inserted=dict(self.inserted),
                    new_business_rows=sum(self.inserted.values()), duplicate_package=False,
                    network_requests=0, watch_writes=0, notifications=0, commands=0, public_events=0)


def apply(package_path, package_sha256, database, *, offline_confirmed=False, now=None, progress=None):
    if not offline_confirmed:
        raise ValueError('offline_writer_confirmation_required')
    package = read_json(package_path, package_sha256)
    if isinstance(package, dict) and package.get('protocol') == PROTOCOL_V2:
        return apply_v2(package, package_sha256, database, now=now, progress=progress)
    *_, captured = validate(package)
    path = location(database, require_exists=True); inspect(path)
    # All source inputs must be ordinary JSON or a separately sealed legacy
    # snapshot. The importer never attaches or opens any other v2 database.
    store = Store(path)
    now = time.time() if now is None else now
    with store.transaction() as db:
        lease = db.execute('SELECT expires_at FROM worker_lease WHERE id=1').fetchone()
        if lease and lease[0] > time.time():
            raise ValueError('stop_all_hunter_writers_before_takeover')
        require_takeover_schema(db)
        refs = proofs(package['ownership'], package['projects'], package['source_sha256'])[3]
        for identifier, project_id in refs.items():
            existing = db.execute('SELECT project_id FROM hunter_takeover_project_refs WHERE x_user_id=?', (identifier,)).fetchone()
            if existing and existing[0] != project_id:
                raise ValueError('canonical_mapping_conflict')
        old = db.execute('SELECT report_json FROM hunter_takeover_runs WHERE package_sha256=?', (package_sha256,)).fetchone()
        if old:
            original = json.loads(old[0])
            return dict(original, duplicate_package=True, inserted={}, new_business_rows=0,
                        original_tables=original['tables'], original_reasons=original['reasons'],
                        tables={name: dict(input=row['input'], imported=0, deduplicated=row['input'], quarantined=0, excluded=0)
                                for name, row in original['tables'].items()}, reasons={'PACKAGE_ALREADY_COMMITTED': sum(len(r) for r in package['rows'].values())})
        if db.execute('SELECT 1 FROM state WHERE key GLOB ? LIMIT 1',(LEGACY_DIRECTORY_PREFIX+'*',)).fetchone():
            raise ValueError('new_v1_apply_forbidden_after_directory_v2')
        clock = watermark(db, now)
        if captured > clock:
            raise ValueError('snapshot_cannot_be_in_future')
        clock = advance(db, now)
        result = Importer(store, db, package, package_sha256, clock).execute(progress)
        db.execute('INSERT INTO hunter_takeover_runs(package_sha256,execution_id,source_sha256,ownership_sha256,projects_sha256,effective_at_us,completed_at_us,report_json) VALUES(?,?,?,?,?,?,?,?)',
                   (package_sha256, EXECUTION, package['source_sha256'], package['ownership_sha256'], package['projects_sha256'],
                    clock, micros(now), canonical(result)))
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('import_database_integrity_failed')
        if progress:
            progress('before_commit')
    if progress:
        progress('after_commit')
    return result


def legacy_hash(namespace, value):
    return hashlib.sha256((namespace+'\0'+str(value)).encode()).hexdigest()


def validate_v2(package):
    exact(package, ('protocol','execution_id','kind','source_sha256','ownership_sha256','projects_sha256','ownership','rows','supplement'))
    if package['protocol'] != PROTOCOL_V2 or package['execution_id'] != EXECUTION or package['kind'] not in ('directory','supplement'):
        raise ValueError('unsupported_directory_protocol')
    sha(package['source_sha256']); sha(package['ownership_sha256'])
    if package['projects_sha256'] != NO_PROJECT_MAP:
        raise ValueError('directory_has_no_canonical_mapping')
    ownership = package['ownership']
    exact(ownership, ('protocol','execution_id','source_sha256','source_manifest_sha256','captured_at','source_stopped','final_watermark_at','approval_sha256','items','target_evidence'))
    if (ownership['protocol'] != 'hunter-takeover-ownership-v2' or ownership['execution_id'] != EXECUTION
            or ownership['source_sha256'] != package['source_sha256'] or ownership['source_stopped'] is not True):
        raise ValueError('directory_source_binding_mismatch')
    for key in ('source_manifest_sha256','approval_sha256'):
        sha(ownership[key])
    captured = instant(ownership['captured_at'])
    cutoff = instant(ownership['final_watermark_at'])
    if cutoff > captured:
        raise ValueError('directory_watermark_invalid')
    decisions, evidence = {}, {}
    for values, group, kind in ((ownership['items'], decisions, 'owner'), (ownership['target_evidence'], evidence, 'target')):
        if not isinstance(values, list) or len(values) > 100000:
            raise ValueError('invalid_directory_proofs')
        for row in values:
            names = ('source_table','source_key_sha256','row_sha256','ownership','evidence_sha256') if kind == 'owner' else (
                'source_table','source_key_sha256','row_sha256','kind','evidence_sha256','event_key_sha256','target_id_sha256','raw_ids')
            exact(row, names)
            for key in ('source_key_sha256','row_sha256','evidence_sha256'):
                sha(row[key])
            if kind == 'owner':
                if row['source_table'] not in ('hunters','alerts') or row['ownership'] not in ('ikun','alpha','unknown'):
                    raise ValueError('invalid_directory_ownership')
            else:
                if row['source_table'] != 'follows' or row['kind'] != 'documented_twId_exact_event_binding':
                    raise ValueError('invalid_directory_target_evidence')
                sha(row['event_key_sha256']); sha(row['target_id_sha256'])
                if not isinstance(row['raw_ids'], list) or not row['raw_ids'] or len(row['raw_ids']) > 1000 or any(type(v) is not int or v < 1 for v in row['raw_ids']) or len(set(row['raw_ids'])) != len(row['raw_ids']):
                    raise ValueError('invalid_directory_raw_references')
            key = (row['source_table'], row['source_key_sha256'])
            if key in group:
                raise ValueError('ambiguous_directory_proof')
            group[key] = row
    exact(package['rows'], FIELDS_V2)
    indexed = {}
    for table, rows in package['rows'].items():
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError('invalid_directory_rows')
        for row in rows:
            exact(row, FIELDS_V2[table])
            key = (table, row_key(table, row))
            if key in indexed:
                raise ValueError('duplicate_source_primary_key')
            indexed[key] = row
    if package['kind'] == 'directory':
        if package['supplement'] is not None:
            raise ValueError('directory_cannot_include_release')
        for group in (decisions, evidence):
            for key, proof in group.items():
                if key not in indexed or digest(indexed[key]) != proof['row_sha256']:
                    raise ValueError('directory_proof_row_mismatch')
        for key, proof in evidence.items():
            row = indexed[key]
            if (row['source'] != '6551_WSS' or proof['event_key_sha256'] != legacy_hash('legacy-event-key-v1',row['event_key'])
                    or proof['target_id_sha256'] != legacy_hash('legacy-id-text-v1',row['target_id'])):
                raise ValueError('directory_target_binding_mismatch')
    elif any(package['rows'].values()) or not isinstance(package['supplement'], dict):
        raise ValueError('supplement_cannot_replay_source_rows')
    return decisions, evidence, captured, cutoff


def prepare_v2(source, source_sha256, ownership_path, ownership_sha256, output):
    """Sealed whitelist export; v2 directory never invents an empty Projects map."""
    source = private_file(source); read_private(source, source_sha256)
    if any(Path(str(source)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
        raise ValueError('source_must_be_sealed_snapshot_without_sidecars')
    ownership = read_json(ownership_path, ownership_sha256)
    rows = {}
    with sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row; db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('legacy_snapshot_integrity_failed')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(FIELDS_V2):
            raise ValueError('unreviewed_legacy_tables')
        for table, fields in FIELDS_V2.items():
            if not set(fields) <= {r[1] for r in db.execute('PRAGMA table_info('+table+')')}:
                raise ValueError('legacy_fields_missing')
            rows[table] = [dict(row) for row in db.execute('SELECT '+','.join(fields)+' FROM '+table)]
    read_private(source, source_sha256)
    package = dict(protocol=PROTOCOL_V2, execution_id=EXECUTION, kind='directory', source_sha256=source_sha256,
                   ownership_sha256=ownership_sha256, projects_sha256=NO_PROJECT_MAP, ownership=ownership, rows=rows, supplement=None)
    validate_v2(package)
    return {'package_sha256': write_package(output, package), 'input': {k:len(v) for k,v in rows.items()},
            'kind':'directory', 'network_requests':0, 'watch_writes':0}


def prepare_supplement_v2(directory, directory_sha256, approval, approval_sha256, profile, profile_sha256, output):
    base = read_json(directory, directory_sha256)
    validate_v2(base)
    if base['kind'] != 'directory':
        raise ValueError('directory_package_required')
    package = dict(base, kind='supplement', rows={k:[] for k in FIELDS}, supplement={
        'approval':read_json(approval,approval_sha256), 'approval_sha256':approval_sha256,
        'profile':read_json(profile,profile_sha256), 'profile_sha256':profile_sha256})
    validate_v2(package)
    validate_supplement(package)
    if package['supplement']['approval']['directory_package_sha256'] != directory_sha256:
        raise ValueError('profile_release_directory_package_mismatch')
    return {'package_sha256':write_package(output,package), 'kind':'supplement', 'network_requests':0, 'watch_writes':0}


def validate_supplement(package):
    supplement = package['supplement']
    exact(supplement, ('approval','approval_sha256','profile','profile_sha256'))
    sha(supplement['approval_sha256']); sha(supplement['profile_sha256'])
    approval, profile = supplement['approval'], supplement['profile']
    exact(approval, ('protocol','execution_id','source_sha256','directory_package_sha256','source_table','source_key_sha256','row_sha256',
                     'prior_receipt_sha256','expected_prior_outcome','account_id','expected_revision','expected_generation','expected_deleted_at','allow_current_identity_only'))
    if (approval['protocol'] != 'hunter-directory-profile-release-v2' or approval['execution_id'] != EXECUTION
            or approval['source_sha256'] != package['source_sha256'] or approval['source_table'] != 'hunters'
            or approval['expected_prior_outcome'] != 'pending_directory' or approval['expected_deleted_at'] is not None
            or type(approval['allow_current_identity_only']) is not bool):
        raise ValueError('invalid_profile_release')
    for key in ('source_key_sha256','row_sha256','directory_package_sha256','prior_receipt_sha256'):
        sha(approval[key])
    for key in ('expected_revision','expected_generation'):
        if type(approval[key]) is not int or approval[key] < 1:
            raise ValueError('invalid_profile_release_revision')
    try:
        if str(uuid.UUID(approval['account_id'])) != approval['account_id']:
            raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise ValueError('invalid_profile_release_account') from None
    exact(profile, ('protocol','provider','operation','requested_handle','returned_handle','id_field','user_id','followers','name','checked_at','evidence_sha256'))
    if (profile['protocol'] != 'hunter-fresh-profile-proof-v1' or profile['provider'] != '6551'
            or profile['operation'] != 'twitter_user_info' or profile['id_field'] not in ('userId','twId')
            or type(profile['followers']) is not int or not 0 <= profile['followers'] <= 9223372036854775807):
        raise ValueError('unproven_fresh_profile_field')
    stable(profile['user_id']); sha(profile['evidence_sha256']); instant(profile['checked_at']); text(profile['name'],200)
    if not re.fullmatch('[1-9][0-9]{0,39}',profile['user_id']):
        raise ValueError('invalid_fresh_user_id')
    if handle(profile['requested_handle']) != handle(profile['returned_handle']):
        raise ValueError('fresh_profile_account_mismatch')
    return approval, profile


def private_state(db, suffix):
    row = db.execute('SELECT value FROM state WHERE key=?', (LEGACY_DIRECTORY_PREFIX+suffix,)).fetchone()
    return json.loads(row[0]) if row else None


def insert_private_state(db, suffix, value):
    old = private_state(db, suffix)
    if old is not None:
        if old != value:
            raise ValueError('legacy_private_fact_conflict')
        return False
    db.execute('INSERT INTO state(key,value) VALUES(?,?)', (LEGACY_DIRECTORY_PREFIX+suffix, canonical(value)))
    return True


class DirectoryImporter:
    def __init__(self, db, package, package_sha256, clock):
        self.db,self.package,self.package_sha256,self.clock = db,package,package_sha256,clock
        self.decisions,self.evidence,self.captured,self.cutoff = validate_v2(package)
        self.inserted = Counter(); self.mapped = {}
        self.tables = {k:Counter(input=len(v)) for k,v in package['rows'].items()}
        self.reasons = Counter()

    def fact(self, table, row):
        key = row_key(table,row)
        value = {'source_sha256':self.package['source_sha256'], 'source_manifest_sha256':self.package['ownership']['source_manifest_sha256'],
                 'source_table':table,'source_key_sha256':key,'row_sha256':digest(row),'row':row}
        if insert_private_state(self.db,'fact:'+table+':'+key,value):
            self.inserted['private_facts'] += 1
        return key,value

    def prior_v1(self, table, key):
        row = self.db.execute('SELECT * FROM hunter_takeover_rows WHERE source_system=? AND source_table=? AND source_key_sha256=?',('legacy-hunter',table,key)).fetchone()
        return dict(row) if row else None

    def pending_hunter(self, row, key):
        owner = self.decisions.get(('hunters',key),{}).get('ownership','unknown')
        if owner != 'ikun':
            return 'excluded' if owner == 'alpha' else 'quarantined','DIRECTORY_OWNERSHIP_UNPROVEN',None
        prior = self.prior_v1('hunters',key)
        v1_hash = digest({name:row[name] for name in FIELDS['hunters']})
        if prior and (prior['row_sha256'] != v1_hash or prior['reason'] == 'ALPHA_EXCLUDED'):
            return 'quarantined','ORIGINAL_DISPOSITION_REQUIRES_REVIEW',None
        username = handle(row['username']); created = instant(row['created_at'])
        if created > self.cutoff:
            raise ValueError('future_directory_creation')
        # Same handle is only a uniqueness conflict, never authority to claim a v2 account.
        existing = self.db.execute('SELECT id FROM hunters WHERE username=?',(username,)).fetchone()
        if existing:
            return 'quarantined','EXISTING_V2_ACCOUNT_PRESERVED',None
        identifier = str(uuid.uuid4())
        self.db.execute("""INSERT INTO hunters(id,username,name,created_at,active_since,enabled,user_id,followers,mode,profile_status,baseline_ready,watch_covered)
            VALUES(?,?,?,?,0,0,NULL,NULL,NULL,'pending',0,0)""",(identifier,username,text(row['display_name'],200),created/1e6))
        self.inserted['hunters'] += 1
        return 'imported','PENDING_DIRECTORY_IMPORTED',identifier

    def row(self, table, row):
        key = row_key(table,row); suffix = 'first:'+table+':'+key
        previous = private_state(self.db,suffix)
        if previous:
            if previous['row_sha256'] != digest(row) or previous['source_sha256'] != self.package['source_sha256']:
                raise ValueError('legacy_first_disposition_conflict')
            outcome,reason,ref = 'deduplicated','SOURCE_CANDIDATE_ALREADY_RECORDED',previous['target_ref']
            if table == 'hunters' and ref:
                self.mapped[handle(row['username'])] = ref
        else:
            outcome,reason,ref = 'quarantined','LEGACY_FACT_HELD_IDENTITY_UNVERIFIED',None
            if table == 'hunters':
                try:
                    outcome,reason,ref = self.pending_hunter(row,key)
                except ValueError:
                    outcome,reason,ref = 'quarantined','INVALID_LEGACY_DIRECTORY_VALUE',None
                if ref:
                    self.mapped[handle(row['username'])] = ref
            owner = self.decisions.get((table,key),{}).get('ownership','unknown') if table in ('hunters','alerts') else None
            receipt = {'source_sha256':self.package['source_sha256'],'source_table':table,'source_key_sha256':key,'row_sha256':digest(row),
                       'package_sha256':self.package_sha256,'outcome':outcome,'reason':reason,'target_ref':ref,
                       'prior_v1':self.prior_v1(table,key),'historical_origin':owner if table=='alerts' else None,
                       'historical_trigger_status':'historical_trigger_unverified' if table=='alerts' else None,
                       'target_evidence':self.evidence.get((table,key)), 'identity_state':'pending',
                       'ownership_evidence':self.decisions.get((table,key))}
            insert_private_state(self.db,suffix,receipt)
            self.inserted['private_receipts'] += 1
            if table == 'hunters' and ref:
                insert_private_state(self.db,'account:'+ref,{'status':'pending','source_key_sha256':key,'row_sha256':digest(row),
                    'source_sha256':self.package['source_sha256'],'directory_package_sha256':self.package_sha256,
                    'first_receipt_sha256':digest(receipt)})
        self.tables[table][outcome] += 1; self.reasons[reason] += 1

    def baselines(self):
        snapshots = defaultdict(list)
        for row in self.package['rows']['twitterapi_following_snapshots']:
            try:snapshots[handle(row['hunter_username'])].append(row)
            except ValueError:pass
        for poll in self.package['rows']['twitterapi_poll_state']:
            try:
                identifier = self.mapped.get(handle(poll['hunter_username']))
                if not identifier:continue
                if self.db.execute('SELECT 1 FROM hunter_takeover_baselines WHERE hunter_id=?',(identifier,)).fetchone():continue
                rows = snapshots[handle(poll['hunter_username'])]
                first = min((instant(r['first_seen_at']) for r in rows),default=None)
                last = max((instant(r['last_seen_at']) for r in rows),default=None)
                success = instant(poll['last_success_at']) if poll['last_success_at'] is not None else None
                if any(v is not None and v > self.cutoff for v in (first,last,success)):continue
                self.db.execute('INSERT INTO hunter_takeover_baselines(hunter_id,source_sha256,snapshot_sha256,snapshot_count,first_seen_at_us,last_seen_at_us,last_success_at_us,ready_proven) VALUES(?,?,?,?,?,?,?,0)',
                    (identifier,self.package['source_sha256'],baseline_digest(rows),len(rows),first,last,success))
                self.inserted['hunter_takeover_baselines'] += 1
            except ValueError:
                pass  # Original invalid evidence remains in immutable private facts.

    def execute(self, progress):
        for table,rows in self.package['rows'].items():
            if table not in ('raw_payloads','metadata'):
                for row in rows:self.fact(table,row)
        if progress:progress('directory_after_facts')
        for table in FIELDS:
            rows = self.package['rows'][table]
            if table in ('raw_payloads','metadata'):
                self.tables[table]['excluded'] += len(rows)
                self.reasons['RAW_OR_OLD_METADATA_EXCLUDED'] += len(rows)
            else:
                for row in rows:self.row(table,row)
            if progress:progress(table)
        self.baselines()
        tables = {k:{name:c[name] for name in ('input',*OUTCOMES)} for k,c in self.tables.items()}
        if any(r['input'] != sum(r[k] for k in OUTCOMES) for r in tables.values()):
            raise ValueError('import_count_reconciliation_failed')
        return {'tables':tables,'reasons':dict(self.reasons),'inserted':dict(self.inserted),'new_business_rows':self.inserted['hunters'],
                'new_private_facts':self.inserted['private_facts'],'new_private_receipts':self.inserted['private_receipts']}


def supplement_profile_v2(db, package, package_sha256, clock):
    approval,profile = validate_supplement(package)
    key = approval['source_key_sha256']; identifier = approval['account_id']
    fact = private_state(db,'fact:hunters:'+key)
    prior = private_state(db,'first:hunters:'+key)
    marker = private_state(db,'account:'+identifier)
    if (not fact or not prior or not marker or marker['status'] != 'pending'
            or fact['row_sha256'] != approval['row_sha256'] or fact['source_sha256'] != package['source_sha256']
            or marker['source_key_sha256'] != key or marker['row_sha256'] != approval['row_sha256']
            or marker['source_sha256'] != package['source_sha256']
            or prior['target_ref'] != identifier or prior['reason'] != 'PENDING_DIRECTORY_IMPORTED'
            or digest(prior) != approval['prior_receipt_sha256'] or marker['first_receipt_sha256'] != digest(prior)
            or prior['package_sha256'] != approval['directory_package_sha256']
            or marker['directory_package_sha256'] != approval['directory_package_sha256']):
        raise ValueError('profile_release_prior_receipt_mismatch')
    row = db.execute('SELECT * FROM hunters WHERE id=?',(identifier,)).fetchone()
    if (not row or row['version'] != approval['expected_revision'] or row['generation'] != approval['expected_generation']
            or row['deleted_at'] != approval['expected_deleted_at'] or row['enabled'] or row['user_id'] is not None
            or row['profile_status'] != 'pending' or handle(profile['requested_handle']) != row['username']):
        raise ValueError('profile_release_account_cas_conflict')
    checked = instant(profile['checked_at'])
    if checked < instant(package['ownership']['captured_at']) or checked > clock or clock-checked > 300_000000:
        raise ValueError('fresh_profile_evidence_stale_or_future')
    if fact['row']['user_id'] != profile['user_id'] and not approval['allow_current_identity_only']:
        raise ValueError('fresh_identity_differs_from_legacy_claim')
    if db.execute('SELECT 1 FROM hunters WHERE user_id=? AND id<>?',(profile['user_id'],identifier)).fetchone():
        raise ValueError('fresh_identity_owned_by_another_account')
    mode = 'WSS' if profile['followers'] >= 5000 else 'REST'
    db.execute("UPDATE hunters SET user_id=?,name=?,followers=?,mode=?,profile_status='ready',next_profile_at=?,version=version+1,generation=generation+1,baseline_ready=0,watch_covered=0 WHERE id=?",
               (profile['user_id'],profile['name'],profile['followers'],mode,checked/1e6+6*3600,identifier))
    proof = {'package_sha256':package_sha256,'approval':approval,'approval_sha256':package['supplement']['approval_sha256'],
             'profile':profile,'profile_sha256':package['supplement']['profile_sha256'],'prior_receipt_sha256':digest(prior),
             'outcome':'verified_current_disabled','historical_identity_binding_confirmed':False,'baseline_ready':False,
             'revision':row['version']+1,'generation':row['generation']+1}
    insert_private_state(db,'proof:'+package['supplement']['approval_sha256'],proof)
    updated = dict(marker,status='verified_current',proof_package_sha256=package_sha256,proof_sha256=digest(proof))
    changed = db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(canonical(updated),LEGACY_DIRECTORY_PREFIX+'account:'+identifier,canonical(marker))).rowcount
    if changed != 1:raise ValueError('profile_release_marker_cas_conflict')
    return {'tables':{},'reasons':{'CURRENT_PROFILE_CONFIRMED_DISABLED':1},'inserted':{'private_profile_proofs':1},
            'new_business_rows':0,'updated_directory_accounts':1,'new_private_facts':0,'new_private_receipts':1}


def apply_v2(package, package_sha256, database, *, now=None, progress=None):
    *_,captured,cutoff = validate_v2(package)
    if package['kind'] == 'supplement':validate_supplement(package)
    path = location(database,require_exists=True); inspect(path)
    store = Store(path); now = time.time() if now is None else now
    with store.transaction() as db:
        lease = db.execute('SELECT expires_at FROM worker_lease WHERE id=1').fetchone()
        if lease and lease[0] > time.time():raise ValueError('stop_all_hunter_writers_before_takeover')
        require_takeover_schema(db)
        previous = db.execute('SELECT report_json FROM hunter_takeover_runs WHERE package_sha256=?',(package_sha256,)).fetchone()
        if previous:
            original = json.loads(previous[0])
            return dict(original,duplicate_package=True,original_result=original,inserted={},new_business_rows=0,
                        updated_directory_accounts=0,new_private_facts=0,new_private_receipts=0,
                        tables={name:dict(input=row['input'],imported=0,deduplicated=row['input'],quarantined=0,excluded=0)
                                for name,row in original['tables'].items()})
        if captured > watermark(db,now):raise ValueError('snapshot_cannot_be_in_future')
        clock = advance(db,now)
        result = (DirectoryImporter(db,package,package_sha256,clock).execute(progress) if package['kind']=='directory'
                  else supplement_profile_v2(db,package,package_sha256,clock))
        result.update(protocol=PROTOCOL_V2,kind=package['kind'],execution_id=EXECUTION,package_sha256=package_sha256,
                      effective_at_us=clock,duplicate_package=False,network_requests=0,watch_writes=0,notifications=0,commands=0,public_events=0)
        db.execute('INSERT INTO hunter_takeover_runs(package_sha256,execution_id,source_sha256,ownership_sha256,projects_sha256,effective_at_us,completed_at_us,report_json) VALUES(?,?,?,?,?,?,?,?)',
                   (package_sha256,EXECUTION,package['source_sha256'],package['ownership_sha256'],NO_PROJECT_MAP,clock,micros(now),canonical(result)))
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('import_database_integrity_failed')
        if progress:progress('before_commit')
    if progress:progress('after_commit')
    return result


def main():
    parser = argparse.ArgumentParser(description='Explicit offline Hunter takeover; no network or Watch operations')
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('prepare')
    for field in ('source', 'source-sha256', 'ownership', 'ownership-sha256', 'projects-map', 'projects-sha256', 'output'):
        export.add_argument('--' + field, required=True)
    ingest = sub.add_parser('apply')
    for field in ('package', 'package-sha256', 'database'):
        ingest.add_argument('--' + field, required=True)
    ingest.add_argument('--offline-confirmed', action='store_true')
    directory = sub.add_parser('prepare-v2')
    for field in ('source','source-sha256','ownership','ownership-sha256','output'):
        directory.add_argument('--'+field,required=True)
    supplement = sub.add_parser('prepare-supplement-v2')
    for field in ('directory','directory-sha256','approval','approval-sha256','profile','profile-sha256','output'):
        supplement.add_argument('--'+field,required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.source, args.source_sha256, args.ownership, args.ownership_sha256,
                             args.projects_map, args.projects_sha256, args.output)
        elif args.command == 'prepare-v2':
            result = prepare_v2(args.source,args.source_sha256,args.ownership,args.ownership_sha256,args.output)
        elif args.command == 'prepare-supplement-v2':
            result = prepare_supplement_v2(args.directory,args.directory_sha256,args.approval,args.approval_sha256,args.profile,args.profile_sha256,args.output)
        else:
            result = apply(args.package, args.package_sha256, args.database, offline_confirmed=args.offline_confirmed)
        print(canonical(result))
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
        # Never print a raw SQL/OS exception containing a private path or row.
        code = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z0-9_]+', str(error)) else 'takeover_input_or_storage_error'
        print(canonical({'error': code, 'network_requests': 0, 'watch_writes': 0}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
