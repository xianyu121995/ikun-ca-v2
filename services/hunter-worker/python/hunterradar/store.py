from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .parsers import Follow, Target, handle

APP_ID = 0x494b0201
WINDOW = 72 * 3600


class Conflict(Exception):
    pass


class Missing(Exception):
    pass


class BudgetExceeded(Exception):
    def __init__(self, retry_at: float):
        self.retry_at = retry_at
        super().__init__('local_budget_or_rate_limit')


class LeaseLost(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path):
        path = path.absolute()
        if path.name != 'hunter.db':
            raise ValueError('database_must_be_named_hunter.db')
        for part in (path, Path(str(path)+'-wal'), Path(str(path)+'-shm'), *path.parents):
            if part.is_symlink():
                raise ValueError('symlinked_database_path_forbidden')
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
            raise ValueError('database_must_be_private_regular_file')
        self.path = path
        self.worker_token = None
        # Check ownership BEFORE schema/WAL mutations. No opening tracking/projects databases.
        if path.exists() and path.stat().st_size:
            with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as db:
                if db.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
                    raise ValueError('foreign_database_refused')
                identity = db.execute('SELECT store_name FROM _store_identity WHERE singleton=1').fetchone()
                if not identity or identity[0] != 'hunter':
                    raise ValueError('store_owner_mismatch')
                if db.execute('PRAGMA user_version').fetchone()[0] not in (0,2):
                    raise ValueError('unsupported_schema_version')
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            schema=Path(__file__).with_name('schema.sql').read_text()
            checksum=hashlib.sha256(schema.encode()).hexdigest()
            db.executescript('BEGIN IMMEDIATE;\n'+schema)
            previous=db.execute('SELECT checksum FROM _hunter_migrations WHERE version=2').fetchone()
            if previous and previous[0]!=checksum:
                raise ValueError('hunter_migration_checksum_mismatch')
            db.execute(f'PRAGMA application_id={APP_ID}')
            db.execute('PRAGMA user_version=2')
            applied=datetime.now(timezone.utc).isoformat()
            db.execute("INSERT OR IGNORE INTO _store_identity VALUES(1,'hunter')")
            db.execute("INSERT OR IGNORE INTO _schema_migrations VALUES(1,'foundation',?)",(applied,))
            db.execute("INSERT OR IGNORE INTO _schema_migrations VALUES(2,'hunterradar_business',?)",(applied,))
            db.execute('INSERT OR IGNORE INTO _hunter_migrations VALUES(2,?,?)',(checksum,applied))
        os.chmod(path, 0o600)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
                if self.worker_token:
                    lease = db.execute('SELECT owner FROM worker_lease WHERE id=1').fetchone()
                    if not lease or lease['owner'] != self.worker_token:
                        raise LeaseLost('worker_lease_lost')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def acquire_worker(self):
        owner, now = str(uuid.uuid4()), time.time()
        with self.connect(True) as db:
            lease = db.execute('SELECT * FROM worker_lease WHERE id=1').fetchone()
            if lease and lease['expires_at'] > now:
                raise RuntimeError('another_hunterradar_worker_owns_this_database')
            db.execute('INSERT INTO worker_lease VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at', (owner,now+15))
        return owner

    def worker_view(self, owner):
        result = copy.copy(self)
        result.worker_token = owner
        return result

    def renew_worker(self):
        with self.connect(True) as db:
            db.execute('UPDATE worker_lease SET expires_at=? WHERE id=1 AND owner=?', (time.time()+15,self.worker_token))

    def release_worker(self, owner):
        with self.connect(True) as db:
            db.execute('DELETE FROM worker_lease WHERE id=1 AND owner=?', (owner,))

    @staticmethod
    def audit(db, actor, action, subject, now, detail=''):
        db.execute('INSERT INTO audit(at,actor,action,subject,detail) VALUES(?,?,?,?,?)',
                   (now, actor, action, subject, detail))

    def hunters(self, include_deleted=False):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM hunters ' + ('' if include_deleted else 'WHERE deleted_at IS NULL ') + 'ORDER BY created_at,id')]

    def hunter(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT * FROM hunters WHERE id=? AND deleted_at IS NULL', (identifier,)).fetchone()
            if not row:
                raise Missing('hunter_not_found')
            return dict(row)

    def add(self, username, note='', actor='local', now=None):
        now = time.time() if now is None else now
        username = handle(username)
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM hunters WHERE username=?', (username,)).fetchone()
            if row:
                if row['deleted_at'] is None:
                    return dict(row)
                db.execute("UPDATE hunters SET deleted_at=NULL,enabled=1,note=?,version=version+1,generation=generation+1,profile_status='pending',next_profile_at=0,baseline_ready=0 WHERE id=?", (note, row['id']))
                identifier = row['id']
            else:
                identifier = str(uuid.uuid4())
                db.execute('INSERT INTO hunters(id,username,note,created_at) VALUES(?,?,?,?)', (identifier, username, note, now))
            self.audit(db, actor, 'hunter.add', identifier, now)
        return self.hunter(identifier)

    def patch(self, identifier, version, *, note=None, enabled=None, delete=False, recheck=False, actor='local', now=None):
        now = time.time() if now is None else now
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM hunters WHERE id=? AND deleted_at IS NULL', (identifier,)).fetchone()
            if not row:
                raise Missing('hunter_not_found')
            if row['version'] != version:
                raise Conflict('stale_hunter_version')
            data = dict(row)
            if note is not None:
                data['note'] = note
            if enabled is not None and bool(enabled) != bool(data['enabled']):
                data.update(enabled=int(enabled), generation=data['generation'] + 1, baseline_ready=0,
                            next_poll_at=0, next_profile_at=0, profile_status='pending',active_since=now)
            if delete:
                data.update(enabled=0, deleted_at=now, generation=data['generation'] + 1, baseline_ready=0)
            if recheck:
                data['next_profile_at'] = 0
            fields = ('note', 'enabled', 'generation', 'baseline_ready', 'next_poll_at', 'next_profile_at', 'profile_status', 'deleted_at','active_since')
            db.execute('UPDATE hunters SET ' + ','.join(k+'=?' for k in fields) + ',version=version+1 WHERE id=?',
                       tuple(data[k] for k in fields) + (identifier,))
            self.audit(db, actor, 'hunter.delete' if delete else 'hunter.update', identifier, now)
        return {'deleted': True, 'id': identifier} if delete else self.hunter(identifier)

    def apply_profile(self, row, user_id, name, followers, now):
        mode = 'WSS' if followers >= 5000 else 'REST'
        with self.connect(True) as db:
            current = db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone()
            if not self.current(current, row):
                return False
            other = db.execute('SELECT id FROM hunters WHERE user_id=? AND id<>?', (user_id, row['id'])).fetchone()
            if other or (current['user_id'] and current['user_id'] != user_id):
                raise Conflict('hunter_stable_identity_conflict')
            changed = current['mode'] != mode
            db.execute("""UPDATE hunters SET user_id=?,name=?,followers=?,mode=?,profile_status='ready',
                next_profile_at=?,profile_failures=0,profile_error=NULL,version=version+1,
                generation=generation+?,baseline_ready=CASE WHEN ? THEN 0 ELSE baseline_ready END,
                next_poll_at=CASE WHEN ? THEN 0 ELSE next_poll_at END WHERE id=?""",
                       (user_id, name, followers, mode, now+6*3600, int(changed), changed, changed, row['id']))
        return True

    @staticmethod
    def current(current, row):
        return current and current['enabled'] and current['deleted_at'] is None and current['generation'] == row['generation']

    def job_failure(self, row, job, code, retry_at):
        assert job in ('profile', 'poll')
        with self.connect(True) as db:
            db.execute(f'UPDATE hunters SET {job}_failures={job}_failures+1,{job}_error=?,next_{job}_at=? WHERE id=? AND generation=? AND enabled=1 AND deleted_at IS NULL',
                       (code, retry_at, row['id'], row['generation']))

    def _insert_event(self, db, row, event: Follow):
        if event.target.username == row['username']:
            return False
        count = db.execute('''INSERT OR IGNORE INTO follow_events(event_key,hunter_id,hunter_x_id,generation,
            target,target_id,target_name,description,occurred_at,received_at,window_at,source,time_basis)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (event.key, row['id'], row['user_id'], row['generation'], event.target.username, event.target.user_id,
             event.target.name, event.target.description, event.occurred_at, event.received_at,
             event.occurred_at, event.source, event.time_basis)).rowcount
        if count:
            qualified = db.execute('SELECT count(DISTINCT hunter_x_id) FROM follow_events WHERE target=? AND window_at>=? AND window_at<=?',
                                   (event.target.username, event.received_at-WINDOW, event.received_at)).fetchone()[0]
            if qualified >= 2:
                db.execute('INSERT OR IGNORE INTO discoveries(target,first_discovered_at) VALUES(?,?)',
                           (event.target.username, event.received_at))
        return bool(count)

    def ingest_wss(self, event: Follow):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM hunters WHERE username=? AND enabled=1 AND deleted_at IS NULL AND mode='WSS' AND profile_status='ready'", (event.hunter,)).fetchone()
            if not row or not row['user_id'] or event.occurred_at < max(row['created_at'],row['active_since']):
                return False
            return self._insert_event(db, row, event)

    def apply_poll(self, row, targets: list[Target], now):
        next_hour = (int(now)//3600+1)*3600
        with self.connect(True) as db:
            current = db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone()
            if not self.current(current, row) or current['mode'] != 'REST' or not current['user_id']:
                return {'discarded': True, 'new': 0}
            count = 0
            for target in targets:
                inserted = db.execute('INSERT OR IGNORE INTO seen_targets(hunter_id,generation,target,user_id) VALUES(?,?,?,?)',
                                      (row['id'], row['generation'], target.username, target.user_id)).rowcount
                if inserted and current['baseline_ready']:
                    key = hashlib.sha256(f"rest:{row['id']}:{row['generation']}:{target.username}".encode()).hexdigest()
                    event = Follow(row['username'], target, now, now, 'TWITTERAPI_IO', key, 'first_observed_after_baseline')
                    count += self._insert_event(db, current, event)
            warning = 'latest_20_may_miss_followings' if len(targets) == 20 else None
            if current['last_poll_at'] and now-current['last_poll_at'] > 7200:
                warning = 'poll_gap_may_miss_followings'
            db.execute('''UPDATE hunters SET baseline_ready=1,last_poll_at=?,next_poll_at=?,poll_failures=0,
                poll_error=NULL,poll_warning=? WHERE id=?''', (now, next_hour, warning, row['id']))
            return {'baseline': not bool(current['baseline_ready']), 'new': count, 'warning': warning}

    def aggregate(self, now=None, limit=200, offset=0):
        now = time.time() if now is None else now
        with self.connect() as db:
            rows = db.execute('''WITH grouped AS (
                SELECT target,count(DISTINCT hunter_x_id) hunter_count,min(window_at) first_seen,max(window_at) last_seen
                FROM follow_events WHERE window_at>=? AND window_at<=? GROUP BY target HAVING count(DISTINCT hunter_x_id)>=2)
                SELECT g.*,d.first_discovered_at activated_at,d.version,d.name review_name,d.description review_description,
                (SELECT target_name FROM follow_events e WHERE e.target=g.target ORDER BY id DESC LIMIT 1) profile_name,
                (SELECT description FROM follow_events e WHERE e.target=g.target ORDER BY id DESC LIMIT 1) profile_bio,
                o.status task_status FROM grouped g JOIN discoveries d USING(target) LEFT JOIN task_outbox o USING(target)
                ORDER BY g.last_seen DESC,g.target LIMIT ? OFFSET ?''', (now-WINDOW, now, limit, offset)).fetchall()
            result = []
            for item in rows:
                item = dict(item)
                item.update(name=item.pop('review_name') or item['profile_name'] or item['target'],
                            description=item.pop('review_description') or item['profile_bio'], origin='real', qualified=True)
                result.append(item)
            return result

    def discovery(self, target):
        with self.connect() as db:
            row = db.execute('SELECT * FROM discoveries WHERE target=?', (handle(target),)).fetchone()
            if not row:
                raise Missing('discovery_not_found')
            result = dict(row)
            event = db.execute('SELECT target_name,description,target_id FROM follow_events WHERE target=? ORDER BY id DESC LIMIT 1', (target,)).fetchone()
            result['profile'] = dict(event) if event else {}
            task = db.execute('SELECT id,status,attempts,last_error,receipt_id,confirmed_at,project_id FROM task_outbox WHERE target=?', (target,)).fetchone()
            result['task'] = dict(task) if task else None
            return result

    def discoveries(self, limit=100, offset=0, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            rows=db.execute('''SELECT d.*,o.status task_status,o.id task_id,o.last_error task_error,
                (SELECT count(DISTINCT hunter_x_id) FROM follow_events e WHERE e.target=d.target AND e.window_at>=? AND e.window_at<=?) hunter_count,
                (SELECT target_name FROM follow_events e WHERE e.target=d.target ORDER BY id DESC LIMIT 1) profile_name,
                (SELECT description FROM follow_events e WHERE e.target=d.target ORDER BY id DESC LIMIT 1) profile_bio
                FROM discoveries d LEFT JOIN task_outbox o USING(target)
                ORDER BY d.first_discovered_at DESC,d.target LIMIT ? OFFSET ?''',(now-WINDOW,now,limit,offset)).fetchall()
            return [dict(row) for row in rows]

    def review(self, target, version, data, actor, now=None):
        target = handle(target)
        with self.connect(True) as db:
            if not db.execute('UPDATE discoveries SET name=?,description=?,website=?,notes=?,rating=?,category=?,stage=?,ignored=?,version=version+1 WHERE target=? AND version=?',
                              (data['name'], data['description'], data['website'], data['notes'], data['rating'],data.get('category','其他'),data.get('stage','未知'),int(data.get('ignored',False)),target, version)).rowcount:
                raise Conflict('stale_discovery_version')
            self.audit(db, actor, 'discovery.review', target, now or time.time())
        return self.discovery(target)

    def confirm(self, target, version, request_key, actor, now=None, *, tenant_id='', protocol='project-task-v1'):
        now = time.time() if now is None else now
        target = handle(target)
        request_hash = hashlib.sha256(json.dumps([target, version,tenant_id,protocol], separators=(',', ':')).encode()).hexdigest()
        with self.connect(True) as db:
            previous = db.execute('SELECT * FROM task_outbox WHERE request_key=?', (request_key,)).fetchone()
            if previous:
                if previous['target'] != target or previous['request_hash'] != request_hash:
                    raise Conflict('idempotency_key_payload_conflict')
                return self.task_dto(previous)
            row = db.execute('SELECT * FROM discoveries WHERE target=?', (target,)).fetchone()
            if not row:
                raise Missing('discovery_not_found')
            if row['version'] != version:
                raise Conflict('stale_discovery_version')
            if not row['name'].strip() or row['ignored']:
                raise Conflict('saved_review_name_required_and_not_ignored')
            count = db.execute('SELECT count(DISTINCT hunter_x_id) FROM follow_events WHERE target=? AND window_at>=? AND window_at<=?', (target, now-WINDOW, now)).fetchone()[0]
            if count < 2:
                raise Conflict('discovery_no_longer_qualified')
            previous = db.execute('SELECT * FROM task_outbox WHERE target=?', (target,)).fetchone()
            if previous:
                return self.task_dto(previous)
            identifier = str(uuid.uuid4())
            event = db.execute('SELECT target_id FROM follow_events WHERE target=? AND target_id IS NOT NULL ORDER BY id DESC LIMIT 1', (target,)).fetchone()
            # Only target information crosses the project boundary. Hunter identities never leave.
            body = {'schema': 'hunterradar.project-task.v1', 'command_id': identifier,
                    'action': 'request_project_monitoring', 'source': 'hunterradar', 'manual_confirmed': True,
                    'confirmed_at': now, 'target': {'username': target, 'x_id_hint': event['target_id'] if event else None},
                    'review': {k: row[k] for k in ('name','description','website','notes','rating','category','stage')}}
            key = 'hunterradar:' + identifier
            if protocol=='v2-event':
                body={'schema_version':1,'event_id':'evt_'+identifier,'source':'hunter',
                      'event_type':'hunter.project_monitoring_requested','occurred_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),
                      'received_at':datetime.fromtimestamp(now,timezone.utc).isoformat(), 'tenant_id':tenant_id,
                      'project_id':None,'correlation_id':'cor_'+identifier,
                      'payload':{'source_entity_key':target,'display_name':row['name'],
                                 'manual_confirmed':True,'review':body['review']}}
                key=identifier
            db.execute('''INSERT INTO task_outbox(id,target,idempotency_key,request_key,request_hash,body,confirmed_by,confirmed_at)
                VALUES(?,?,?,?,?,?,?,?)''', (identifier, target, key, request_key, request_hash, json.dumps(body, ensure_ascii=False, separators=(',', ':')), actor, now))
            db.execute('UPDATE discoveries SET version=version+1 WHERE target=?', (target,))
            self.audit(db, actor, 'project_task.confirm', target, now)
            return {'id': identifier, 'status': 'pending', 'receipt_id': None, 'attempts': 0}

    @staticmethod
    def task_dto(row):
        return {key: row[key] for key in ('id', 'status', 'receipt_id', 'attempts')}

    def recover(self):
        with self.connect(True) as db:
            db.execute("UPDATE task_outbox SET status='pending' WHERE status='delivering'")

    def claim_task(self, now):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM task_outbox WHERE status IN ('pending','unknown') AND next_attempt_at<=? ORDER BY confirmed_at LIMIT 1", (now,)).fetchone()
            if row:
                db.execute("UPDATE task_outbox SET status='delivering',attempts=attempts+1 WHERE id=?", (row['id'],))
                return dict(row) | {'attempts': row['attempts']+1}

    def finish_task(self, identifier, status, *, code=None, retry_at=0, receipt=None, now=None,canonical=None):
        with self.connect(True) as db:
            db.execute('UPDATE task_outbox SET status=?,last_error=?,next_attempt_at=?,receipt_id=?,delivered_at=?,project_id=COALESCE(?,project_id) WHERE id=?',
                       (status, code, retry_at, receipt, now if status == 'delivered' else None, canonical,identifier))

    def retry_task(self, identifier, actor):
        with self.connect(True) as db:
            if not db.execute("UPDATE task_outbox SET status='pending',next_attempt_at=0,last_error=NULL WHERE id=? AND status='failed'", (identifier,)).rowcount:
                raise Conflict('task_not_failed')
            self.audit(db, actor, 'project_task.retry', identifier, time.time())

    def reserve(self, provider, cost, daily_limit, rpm, now):
        day = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d')
        minute = str(int(now)//60)
        with self.connect(True) as db:
            for label, amount, cap, retry_at in ((day, cost, daily_limit, (int(now)//86400+1)*86400),
                                                ('minute:'+minute, 1, rpm, (int(now)//60+1)*60)):
                row = db.execute('SELECT reserved FROM quota WHERE provider=? AND window=?', (provider, label)).fetchone()
                if row and row[0]+amount > cap or amount > cap:
                    raise BudgetExceeded(retry_at)
                db.execute('INSERT INTO quota VALUES(?,?,?) ON CONFLICT(provider,window) DO UPDATE SET reserved=reserved+excluded.reserved', (provider, label, amount))
            db.execute("DELETE FROM quota WHERE window LIKE 'minute:%' AND window<>?", ('minute:'+minute,))

    def set_state(self, key, value):
        with self.connect(True) as db:
            db.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

    def states(self):
        with self.connect() as db:
            return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM state')}

    def coverage(self, usernames, now):
        with self.connect(True) as db:
            db.execute('UPDATE hunters SET watch_covered=0')
            db.executemany('UPDATE hunters SET watch_covered=1 WHERE username=?', [(name,) for name in usernames])
        self.set_state('watch_checked_at', now)

    def status(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            today = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d')
            counts = {r['status']: r['n'] for r in db.execute('SELECT status,count(*) n FROM task_outbox GROUP BY status')}
            quotas = {r['provider']: r['reserved'] for r in db.execute('SELECT * FROM quota WHERE window=?', (today,))}
            events = db.execute('SELECT count(*) FROM follow_events').fetchone()[0]
        states = self.states()
        alive = now - states.get('worker_heartbeat', 0) < 15
        return {'worker_alive': alive, 'wss_state': states.get('wss_state', 'stopped') if alive else 'stopped',
                'last_pong_at': states.get('last_pong_at'), 'worker_error': states.get('worker_error'),
                'watch_checked_at': states.get('watch_checked_at'), 'watch_error': states.get('watch_error'),
                'events': events, 'tasks': counts, 'daily_reserved': quotas,
                'window_hours': 72, 'distinct_hunters_required': 2, 'rest_interval_seconds': 3600, 'rest_page_size': 20}
