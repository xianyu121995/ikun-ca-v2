from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
import copy
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .parsers import Follow, Target, handle
from .migration import location, inspect, migrate
from .retention import advance,active,retired,micros,TTL_US

APP_ID = 0x494b0201
WINDOW = 72 * 3600
LEGACY_DIRECTORY_PREFIX = 'legacy_takeover_v2:'
# Enrichment caches that are only ever reused for one hour (providers.py / ai_prefill.py).
# Each entry maps a key prefix to the JSON field holding its write time.
# Billing fences (provider_intent:*), provider blocks, followings/profile results,
# cooldowns, REST batches and Watch state are deliberately NOT listed here.
EXPIRING_CACHE_PREFIXES = (('provider_result:tweets:', 'received_at'),
                           ('provider_result:ai_profile:', 'received_at'),
                           ('ai_input:', 'at'))
# Code only reuses enrichment caches younger than this; prune must never go below it.
CACHE_REUSE_WINDOW_SECONDS = 3600
# Default prune retention (72h). Larger than the reuse window so recent caches stay for triage.
CACHE_RETENTION_SECONDS = 72 * 3600
# How often retention_loop may call prune_expired_caches (store.cleanup stays ~60s).
CACHE_PRUNE_INTERVAL_SECONDS = 24 * 3600
PROTECTED_STATE_PREFIXES = ('provider_intent:', 'provider_result:followings:', 'provider_result:profile:',
                            'cooldown:', 'rest_batches:', 'rest_cutover:', 'watch', LEGACY_DIRECTORY_PREFIX)
ACTIVE_TRANSACTION=ContextVar('hunter_transaction',default=None)


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
    def __init__(self, path: Path, *, initialize=False):
        self.path = location(path)
        self.worker_token = None
        if initialize:migrate(self.path)
        inspect(self.path)

    def inspect(self):
        return inspect(self.path)

    @contextmanager
    def connect(self, write=False):
        active=ACTIVE_TRANSACTION.get()
        if active is not None:
            if active[0]!=self.path:raise ValueError('cross_store_transaction_forbidden')
            yield active[1]
            return
        location(self.path,require_exists=True)
        db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=5)
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

    @contextmanager
    def transaction(self):
        with self.connect(True) as db:
            token=ACTIVE_TRANSACTION.set((self.path,db))
            try:yield db
            finally:ACTIVE_TRANSACTION.reset(token)

    def retention_clock(self,now=None):
        with self.connect(True) as db:return advance(db,time.time() if now is None else now)/1e6

    def cleanup(self,now=None,**kwargs):
        from .retention import cleanup,prune_bundles,watermark
        try:return cleanup(self,now,**kwargs)
        except BaseException:
            try:
                with self.connect() as db:stamp=watermark(db,time.time() if now is None else now)
                prune_bundles(self.path,stamp)
            except (OSError,ValueError,sqlite3.Error):pass
            raise

    def change(self,db,target,now,*,initial=False):
        from .formal import discovery_dto
        row=db.execute('SELECT * FROM discoveries WHERE target=?',(target,)).fetchone()
        if not active(db,row,now):return
        data=discovery_dto(db,target,now)
        db.execute('INSERT INTO public_changes(type,entity_id,data,received_at,initial_publication) VALUES(?,?,?,?,?)',
                   ('hunter.discovery.updated',data['discovery_id'],json.dumps(data,ensure_ascii=False),now,int(initial)))

    def establish_wss_baseline(self,rows,now):
        with self.connect(True) as db:
            for row in rows:
                db.execute("UPDATE hunters SET baseline_ready=1,baseline_at=? WHERE id=? AND generation=? AND enabled=1 AND deleted_at IS NULL AND mode='WSS' AND baseline_ready=0",(now,row['id'],row['generation']))

    def acquire_worker(self):
        owner, now = str(uuid.uuid4()), time.time()
        with self.connect(True) as db:
            lease = db.execute('SELECT * FROM worker_lease WHERE id=1').fetchone()
            if lease and lease['expires_at'] > now:
                raise RuntimeError('another_hunterradar_worker_owns_this_database')
            db.execute('INSERT INTO worker_lease(id,owner,expires_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at', (owner,now+15))
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

    def add(self, username, note='', actor='local', now=None, *, label='',enabled=True):
        now = time.time() if now is None else now
        username = handle(username)
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM hunters WHERE username=?', (username,)).fetchone()
            if row:
                if row['deleted_at'] is None:
                    return dict(row)
                if self.legacy_identity_pending(db, row['id']):
                    raise Conflict('legacy_identity_pending_review')
                db.execute("UPDATE hunters SET deleted_at=NULL,enabled=?,note=?,label=?,version=version+1,generation=generation+1,baseline_ready=0,baseline_at=NULL,active_since=? WHERE id=?", (int(enabled),note,label,now,row['id']))
                identifier = row['id']
            else:
                identifier = str(uuid.uuid4())
                db.execute('INSERT INTO hunters(id,username,note,label,enabled,created_at,active_since) VALUES(?,?,?,?,?,?,?)', (identifier, username, note,label,int(enabled),now,now))
            self.audit(db, actor, 'hunter.add', identifier, now)
        return self.hunter(identifier)

    def patch(self, identifier, version, *, note=None, label=None,enabled=None, delete=False, recheck=False, actor='local', now=None):
        now = time.time() if now is None else now
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM hunters WHERE id=? AND deleted_at IS NULL', (identifier,)).fetchone()
            if not row:
                raise Missing('hunter_not_found')
            if row['version'] != version:
                raise Conflict('stale_hunter_version')
            if enabled and self.legacy_identity_pending(db, identifier):
                raise Conflict('legacy_identity_pending_review')
            data = dict(row)
            if note is not None:
                data['note'] = note
            if label is not None:data['label']=label
            if enabled is not None and bool(enabled) != bool(data['enabled']):
                data.update(enabled=int(enabled), generation=data['generation'] + 1, baseline_ready=0,
                            next_poll_at=0, active_since=now,baseline_at=None)
            if delete:
                data.update(enabled=0, deleted_at=now, generation=data['generation'] + 1, baseline_ready=0,baseline_at=None)
            if recheck and data['profile_status'] != 'ready':
                data['next_profile_at'] = 0
                # Recheck is an explicit account action, not a provider-wide
                # payment unblock. Only this account's permanent request blocks.
                for operation, job in (('profile', 'profile'), ('followings', 'poll')):
                    key = self.provider_block_keys(operation, row['username'])[1]
                    saved = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
                    block = json.loads(saved[0]) if saved else None
                    if block and block['state'] == 'blocked' and block['code'] in ('provider_http_400', 'provider_http_404'):
                        self._release_provider_block(db, key, block, actor, 'account_recheck', now)
                        data[job+'_error'] = None
                        data['next_'+job+'_at'] = 0
            fields = ('note','label', 'enabled', 'generation', 'baseline_ready','baseline_at', 'next_poll_at', 'next_profile_at', 'profile_status', 'deleted_at','active_since','profile_error','poll_error')
            db.execute('UPDATE hunters SET ' + ','.join(k+'=?' for k in fields) + ',version=version+1 WHERE id=?',
                       tuple(data[k] for k in fields) + (identifier,))
            self.audit(db, actor, 'hunter.delete' if delete else 'hunter.update', identifier, now)
        return {'deleted': True, 'id': identifier} if delete else self.hunter(identifier)

    def adopt_legacy_profile(self, identifier, version, profile, actor='owner-approved-activation'):
        """Use the owner's approved historical profile without claiming a fresh provider lookup."""
        with self.connect(True) as db:
            row=db.execute('SELECT * FROM hunters WHERE id=? AND deleted_at IS NULL',(identifier,)).fetchone()
            if not row or row['version']!=version:raise Conflict('stale_hunter_version')
            if handle(profile['username'])!=row['username'] or not str(profile['user_id']).isdigit() or type(profile['followers']) is not int or profile['followers']<0 or profile['monitor_mode'] not in ('WSS','REST'):
                raise ValueError('invalid_approved_legacy_profile')
            key=LEGACY_DIRECTORY_PREFIX+'account:'+identifier
            marker=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
            if not marker:raise Conflict('not_a_migrated_directory_account')
            other=db.execute('SELECT id FROM hunters WHERE user_id=? AND id<>?',(str(profile['user_id']),identifier)).fetchone()
            if other or (row['user_id'] and row['user_id']!=str(profile['user_id'])):raise Conflict('hunter_stable_identity_conflict')
            if row['profile_status']=='ready':return dict(row)
            marker=json.loads(marker[0]);marker.update(status='owner_accepted_legacy',profile_source='approved_migration_snapshot')
            db.execute('UPDATE state SET value=? WHERE key=?',(json.dumps(marker),key))
            db.execute("UPDATE hunters SET user_id=?,name=?,followers=?,mode=?,profile_status='ready',next_profile_at=9999999999,profile_error=NULL,profile_failures=0,version=version+1 WHERE id=?",(str(profile['user_id']),profile.get('display_name') or row['username'],profile['followers'],profile['monitor_mode'],identifier))
            self.audit(db,actor,'hunter.adopt_legacy_profile',identifier,time.time())
        return self.hunter(identifier)

    def apply_profile(self, row, user_id, name, followers, now, *, rest_only=False):
        mode = 'WSS' if followers >= 5000 and not rest_only else 'REST'
        with self.connect(True) as db:
            current = db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone()
            if not self.current(current, row):
                return False
            other = db.execute('SELECT id FROM hunters WHERE user_id=? AND id<>?', (user_id, row['id'])).fetchone()
            if other or (current['user_id'] and current['user_id'] != user_id):
                raise Conflict('hunter_stable_identity_conflict')
            if current['profile_status'] == 'ready':
                return False
            changed = current['mode'] != mode
            db.execute("""UPDATE hunters SET user_id=?,name=?,followers=?,mode=?,profile_status='ready',
                next_profile_at=?,profile_failures=0,profile_error=NULL,version=version+1,
                generation=generation+?,baseline_ready=CASE WHEN ? THEN 0 ELSE baseline_ready END,
                baseline_at=CASE WHEN ? THEN ? ELSE baseline_at END,
                active_since=CASE WHEN ? THEN ? ELSE active_since END,
                next_poll_at=CASE WHEN ? THEN 0 ELSE next_poll_at END WHERE id=?""",
                       (user_id, name, followers, mode, 9999999999, int(changed), changed,changed,now,changed,now,changed, row['id']))
            db.execute('DELETE FROM state WHERE key=?', ('provider_result:profile:'+hashlib.sha256(row['username'].encode()).hexdigest(),))
        return True

    @staticmethod
    def current(current, row):
        return current and current['enabled'] and current['deleted_at'] is None and current['generation'] == row['generation']

    def job_failure(self, row, job, code, retry_at):
        assert job in ('profile', 'poll')
        with self.connect(True) as db:
            next_time = f',next_{job}_at=?' if retry_at is not None else ''
            values = (code, retry_at) if retry_at is not None else (code,)
            db.execute(f'UPDATE hunters SET {job}_failures={job}_failures+1,{job}_error=?{next_time} WHERE id=? AND generation=? AND enabled=1 AND deleted_at IS NULL',
                       (*values, row['id'], row['generation']))
            if job=='profile' and code=='stable_identity_conflict':
                db.execute("UPDATE hunters SET profile_status='pending',baseline_ready=0,generation=generation+1 WHERE id=? AND generation=?",(row['id'],row['generation']))

    def resolve_target(self,db,target:Target,observed_at):
        alias=db.execute('SELECT i.* FROM target_identities i JOIN target_aliases a USING(entity_key) WHERE a.x_handle=?',(target.username,)).fetchone()
        identity=db.execute('SELECT * FROM target_identities WHERE x_user_id=?',(target.user_id,)).fetchone() if target.user_id else None
        if alias and target.user_id and alias['x_user_id'] and alias['x_user_id']!=target.user_id:raise Conflict('target_stable_identity_conflict')
        if alias and identity and alias['entity_key']!=identity['entity_key']:raise Conflict('target_alias_conflict')
        current=identity or alias
        if current:
            db.execute('UPDATE target_identities SET x_user_id=COALESCE(x_user_id,?),current_handle=CASE WHEN updated_at<=? THEN ? ELSE current_handle END,updated_at=max(updated_at,?) WHERE entity_key=?',(target.user_id,observed_at,target.username,observed_at,current['entity_key']))
            db.execute('INSERT OR IGNORE INTO target_aliases(x_handle,entity_key) VALUES(?,?)',(target.username,current['entity_key']))
            return current['anchor']
        entity='tgt_'+str(uuid.uuid4())
        db.execute('INSERT INTO target_identities(entity_key,anchor,x_user_id,current_handle,updated_at) VALUES(?,?,?,?,?)',(entity,target.username,target.user_id,target.username,observed_at))
        db.execute('INSERT INTO target_aliases(x_handle,entity_key) VALUES(?,?)',(target.username,entity))
        return target.username

    def _insert_event(self, db, row, event: Follow):
        stamp=advance(db,event.received_at)
        effective=stamp/1e6
        if event.occurred_at<effective-WINDOW:return False
        if retired(db,event.target.user_id,event.received_at):return False
        ledger=db.execute('SELECT discovery_id FROM target_discovery_ledger WHERE x_user_id=?',(event.target.user_id,)).fetchone() if event.target.user_id else None
        if ledger and not db.execute('SELECT 1 FROM discoveries WHERE discovery_id=?',(ledger[0],)).fetchone():raise Conflict('discovery_ledger_requires_recovery')
        if event.target.username == row['username'] or (event.target.user_id and event.target.user_id==row['user_id']):
            return False
        existing=db.execute('SELECT anchor FROM target_identities WHERE x_user_id=? OR entity_key=(SELECT entity_key FROM target_aliases WHERE x_handle=?)',(event.target.user_id,event.target.username)).fetchall()
        if event.source=='6551_WSS' and any(db.execute('SELECT 1 FROM follow_events WHERE hunter_x_id=? AND target=? AND occurred_at=? AND source=?',(row['user_id'],item['anchor'],event.occurred_at,event.source)).fetchone() for item in existing):return False
        target=self.resolve_target(db,event.target,event.occurred_at)
        if event.source=='6551_WSS' and db.execute('SELECT 1 FROM follow_events WHERE hunter_x_id=? AND target=? AND occurred_at=? AND source=?',(row['user_id'],target,event.occurred_at,event.source)).fetchone():return False
        count = db.execute('''INSERT OR IGNORE INTO follow_events(event_key,hunter_id,hunter_x_id,generation,
            target,target_id,target_name,description,occurred_at,received_at,window_at,source,time_basis)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (event.key, row['id'], row['user_id'], row['generation'], target, event.target.user_id,
             event.target.name, event.target.description, event.occurred_at, event.received_at,
             micros(event.occurred_at)/1e6, event.source, event.time_basis)).rowcount
        if count:
            qualified = db.execute('SELECT count(DISTINCT hunter_x_id) FROM follow_events WHERE target=? AND target_id IS NOT NULL AND window_at>=? AND window_at<=?',
                                   (target, effective-WINDOW, effective)).fetchone()[0]
            if qualified >= 2 and event.target.user_id:
                identifier='dsc_'+str(uuid.uuid4())
                created=db.execute('INSERT OR IGNORE INTO target_discovery_ledger(scope,platform,x_user_id,discovery_id,first_discovered_at_us) VALUES(?,?,?,?,?)',('ikun-main','x',event.target.user_id,identifier,stamp)).rowcount
                if created:
                    db.execute('INSERT INTO discoveries(target,first_discovered_at,discovery_id,updated_at,first_discovered_at_us,profile_json) VALUES(?,?,?,?,?,?)',
                               (target,stamp/1e6,identifier,event.received_at,stamp,json.dumps({'target_name':event.target.name,'description':event.target.description})))
                elif not db.execute('SELECT 1 FROM discoveries WHERE target=?',(target,)).fetchone():
                    raise Conflict('discovery_ledger_requires_recovery')
                else:db.execute('UPDATE discoveries SET version=version+1,updated_at=? WHERE target=?',(event.received_at,target))
                self.change(db,target,effective,initial=bool(created))
        return bool(count)

    def ingest_wss(self, event: Follow, *, generation=None):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM hunters WHERE username=? AND enabled=1 AND deleted_at IS NULL AND mode='WSS' AND profile_status='ready'", (event.hunter,)).fetchone()
            if not row or (generation is not None and generation!=row['generation']) or not row['user_id'] or not row['baseline_ready'] or event.occurred_at < max(row['created_at'],row['active_since'],row['baseline_at'] or 0):
                return False
            return self._insert_event(db, row, event)

    def apply_rest_cutover(self, row, targets: list[Target], now, *, next_poll_at=None):
        """Seed a NEW REST generation atomically; never turn WSS history into alerts.

        Called by the sole worker, only after a valid paid REST response exists.
        External Watch cleanup is a separate, explicitly verified operator step.
        """
        with self.transaction() as db:
            current = db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone()
            if not self.current(current, row) or current['version'] != row['version'] or current['mode'] != 'WSS' or current['profile_status'] != 'ready':
                return {'discarded': True, 'new': 0}
            db.execute("""UPDATE hunters SET mode='REST',generation=generation+1,version=version+1,
                baseline_ready=0,baseline_at=?,active_since=? WHERE id=?""", (now, now, row['id']))
            migrated = dict(db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone())
            result = self.apply_poll(migrated, targets, now, next_poll_at=next_poll_at)
            self.set_state('rest_cutover:'+row['id'], {'from_generation':row['generation'],
                'generation':migrated['generation'], 'baseline_at':now, 'watch_cleanup':'pending'})
            self.audit(db, 'worker', 'hunter.rest_cutover', row['id'], now, 'baseline_only;watch_writes=0')
            return dict(result, migrated=True)

    def apply_poll(self, row, targets: list[Target], now, *, next_poll_at=None):
        next_hour = now+3600 if next_poll_at is None else next_poll_at
        with self.connect(True) as db:
            current = db.execute('SELECT * FROM hunters WHERE id=?', (row['id'],)).fetchone()
            if not self.current(current, row) or current['mode'] != 'REST' or not current['user_id']:
                return {'discarded': True, 'new': 0}
            count = 0
            for target in targets:
                if retired(db,target.user_id,now):continue
                anchor=self.resolve_target(db,target,now)
                inserted = db.execute('INSERT OR IGNORE INTO seen_targets(hunter_id,generation,target,user_id) VALUES(?,?,?,?)',
                                      (row['id'], row['generation'], anchor, target.user_id)).rowcount
                if inserted and current['baseline_ready']:
                    key = hashlib.sha256(f"rest:{row['id']}:{row['generation']}:{target.username}".encode()).hexdigest()
                    event = Follow(row['username'], target, now, now, 'TWITTERAPI_IO', key, 'first_observed_after_baseline')
                    count += self._insert_event(db, current, event)
            warning = 'latest_20_may_miss_followings' if len(targets) == 20 else None
            if current['last_poll_at'] and now-current['last_poll_at'] > 7200:
                warning = 'poll_gap_may_miss_followings'
            db.execute('''UPDATE hunters SET baseline_ready=1,last_poll_at=?,next_poll_at=?,poll_failures=0,
                poll_error=NULL,poll_warning=? WHERE id=?''', (now, next_hour, warning, row['id']))
            # Consume the paid response atomically with its baseline/events and hourly schedule.
            db.execute('DELETE FROM state WHERE key=?', ('provider_result:followings:'+hashlib.sha256(row['username'].encode()).hexdigest(),))
            return {'baseline': not bool(current['baseline_ready']), 'new': count, 'warning': warning}

    def aggregate(self, now=None, limit=200, offset=0):
        now = time.time() if now is None else now
        clock=self.retention_clock(now)
        now=clock
        with self.connect() as db:
            rows = db.execute('''WITH grouped AS (
                SELECT target,count(DISTINCT hunter_x_id) hunter_count,min(window_at) first_seen,max(window_at) last_seen
                FROM follow_events WHERE target_id IS NOT NULL AND window_at>=? AND window_at<=? GROUP BY target HAVING count(DISTINCT hunter_x_id)>=2)
                SELECT g.*,d.first_discovered_at activated_at,d.version,d.name review_name,d.description review_description,
                (SELECT target_name FROM follow_events e WHERE e.target=g.target ORDER BY id DESC LIMIT 1) profile_name,
                (SELECT description FROM follow_events e WHERE e.target=g.target ORDER BY id DESC LIMIT 1) profile_bio,
                o.status task_status FROM grouped g JOIN discoveries d USING(target) LEFT JOIN task_outbox o USING(target)
                WHERE d.first_discovered_at_us>? ORDER BY g.last_seen DESC,g.target LIMIT ? OFFSET ?''', (now-WINDOW, now, micros(clock)-TTL_US,limit, offset)).fetchall()
            result = []
            for item in rows:
                item = dict(item)
                item.update(name=item.pop('review_name') or item['profile_name'] or item['target'],
                            description=item.pop('review_description') or item['profile_bio'], origin='real', qualified=True)
                result.append(item)
            return result

    def discovery(self, target):
        now=self.retention_clock()
        with self.connect() as db:
            row = db.execute('SELECT * FROM discoveries WHERE target=?', (handle(target),)).fetchone()
            if not active(db,row,now):
                raise Missing('discovery_not_found')
            result = dict(row)
            event = db.execute('SELECT target_name,description,target_id FROM follow_events WHERE target=? ORDER BY id DESC LIMIT 1', (target,)).fetchone()
            result['profile'] = dict(event) if event else {}
            task = db.execute('SELECT id,status,attempts,last_error,receipt_id,confirmed_at,project_id FROM task_outbox WHERE target=?', (target,)).fetchone()
            result['task'] = dict(task) if task else None
            return result

    def discoveries(self, limit=100, offset=0, now=None):
        now = time.time() if now is None else now
        clock=self.retention_clock(now)
        now=clock
        with self.connect() as db:
            rows=db.execute('''SELECT d.*,o.status task_status,o.id task_id,o.last_error task_error,
                (SELECT count(DISTINCT hunter_x_id) FROM follow_events e WHERE e.target=d.target AND e.target_id IS NOT NULL AND e.window_at>=? AND e.window_at<=?) hunter_count,
                (SELECT target_name FROM follow_events e WHERE e.target=d.target ORDER BY id DESC LIMIT 1) profile_name,
                (SELECT description FROM follow_events e WHERE e.target=d.target ORDER BY id DESC LIMIT 1) profile_bio
                FROM discoveries d LEFT JOIN task_outbox o USING(target)
                WHERE d.first_discovered_at_us>? ORDER BY d.first_discovered_at DESC,d.target LIMIT ? OFFSET ?''',(now-WINDOW,now,micros(clock)-TTL_US,limit,offset)).fetchall()
            return [dict(row) for row in rows]

    def review(self, target, version, data, actor, now=None):
        target = handle(target)
        with self.connect(True) as db:
            if not active(db,db.execute('SELECT * FROM discoveries WHERE target=?',(target,)).fetchone(),now or time.time()):raise Missing('discovery_not_found')
            if not db.execute('UPDATE discoveries SET name=?,description=?,website=?,notes=?,rating=?,category=?,stage=?,ignored=?,version=version+1 WHERE target=? AND version=?',
                              (data['name'], data['description'], data['website'], data['notes'], data['rating'],data.get('category','其他'),data.get('stage','未知'),int(data.get('ignored',False)),target, version)).rowcount:
                raise Conflict('stale_discovery_version')
            self.audit(db, actor, 'discovery.review', target, now or time.time())
        return self.discovery(target)

    def confirm(self, target, version, request_key, actor, now=None, *, tenant_id='', protocol='project-task-v1'):
        if protocol=='v2-event':raise ValueError('use_formal_confirmed_monitoring_request')
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
            if not active(db,row,now):
                raise Missing('discovery_not_found')
            if row['version'] != version:
                raise Conflict('stale_discovery_version')
            if not row['name'].strip() or row['ignored']:
                raise Conflict('saved_review_name_required_and_not_ignored')
            count = db.execute('SELECT count(DISTINCT hunter_x_id) FROM follow_events WHERE target=? AND target_id IS NOT NULL AND window_at>=? AND window_at<=?', (target, now-WINDOW, now)).fetchone()[0]
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
            db.execute("UPDATE task_outbox SET status=CASE WHEN posted=1 THEN 'unknown' ELSE 'pending' END,public_state=CASE WHEN posted=1 THEN 'unknown' ELSE 'pending' END WHERE status='delivering'")

    def claim_task(self, now):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM task_outbox WHERE status IN ('pending','unknown') AND next_attempt_at<=? ORDER BY confirmed_at LIMIT 1", (now,)).fetchone()
            if row:
                db.execute("UPDATE task_outbox SET status='delivering',attempts=attempts+1,command_revision=command_revision+1,updated_at=? WHERE id=?", (now,row['id']))
                return dict(row) | {'attempts': row['attempts']+1}

    def due_delivered_outcomes(self, now, limit=40):
        """Delivered joins whose public state is not terminal. Keyed rows only; no body."""
        with self.connect() as db:
            rows=db.execute('''SELECT id,event_id,command_id,public_state FROM task_outbox
                WHERE status='delivered' AND posted=1 AND command_id IS NOT NULL AND event_id IS NOT NULL
                  AND public_state IN ('pending','accepted','running','unknown') AND next_attempt_at<=?
                ORDER BY next_attempt_at,confirmed_at LIMIT ?''',(now,int(limit))).fetchall()
            return [dict(row) for row in rows]

    def apply_delivered_outcomes(self, updates, now):
        """Persist a projects command outcome. Never changes status, posted, or attempts."""
        with self.connect(True) as db:
            for identifier,state,error,retry_at in updates:
                row=db.execute("SELECT * FROM task_outbox WHERE id=? AND status='delivered' AND posted=1",(identifier,)).fetchone()
                if not row or row['public_state'] in ('succeeded','failed'):continue
                if state not in ('pending','accepted','running','succeeded','failed','unknown'):
                    db.execute("UPDATE task_outbox SET next_attempt_at=? WHERE id=? AND status='delivered' AND posted=1",(retry_at,identifier))
                    continue
                stored=error if state in ('failed','unknown') else None
                changed=row['public_state']!=state or (row['last_error'] or None)!=(stored or None)
                if not changed:
                    db.execute("UPDATE task_outbox SET next_attempt_at=? WHERE id=? AND status='delivered' AND posted=1",(retry_at,identifier))
                    continue
                db.execute('''UPDATE task_outbox SET public_state=?,last_error=?,next_attempt_at=?,updated_at=?,command_revision=command_revision+1
                    WHERE id=? AND status='delivered' AND posted=1''',(state,stored,retry_at,now,identifier))
                task=db.execute('SELECT * FROM task_outbox WHERE id=?',(identifier,)).fetchone()
                if task and task['command_id']:
                    from .formal import command_dto
                    db.execute('INSERT INTO public_changes(type,entity_id,data,received_at) VALUES(?,?,?,?)',('command.updated',task['command_id'],json.dumps(command_dto(task,task['request_id'])),now))
                    if task['target']:self.change(db,task['target'],now)

    def finish_task(self, identifier, status, *, code=None, retry_at=0, receipt=None, now=None,canonical=None,receipt_data=None):
        with self.connect(True) as db:
            stamp=time.time() if now is None else now
            db.execute('UPDATE task_outbox SET status=?,public_state=?,last_error=?,next_attempt_at=?,receipt_id=?,delivered_at=?,project_id=COALESCE(?,project_id),updated_at=?,command_revision=command_revision+1 WHERE id=?',
                       (status,'pending' if status in ('pending','delivered','delivering') else status,code,retry_at,receipt,stamp if status=='delivered' else None,canonical,stamp,identifier))
            if receipt_data is not None:db.execute('UPDATE task_outbox SET receipt_json=? WHERE id=?',(json.dumps(receipt_data,sort_keys=True),identifier))
            task=db.execute('SELECT * FROM task_outbox WHERE id=?',(identifier,)).fetchone()
            if task and task['command_id']:
                from .formal import command_dto
                db.execute('INSERT INTO public_changes(type,entity_id,data,received_at) VALUES(?,?,?,?)',('command.updated',task['command_id'],json.dumps(command_dto(task,task['request_id'])),stamp))
                if task['target']:self.change(db,task['target'],stamp)

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
                db.execute('INSERT INTO quota(provider,window,reserved) VALUES(?,?,?) ON CONFLICT(provider,window) DO UPDATE SET reserved=reserved+excluded.reserved', (provider, label, amount))
            db.execute("DELETE FROM quota WHERE window LIKE 'minute:%' AND window<>?", ('minute:'+minute,))

    @staticmethod
    def provider_block_keys(operation, username=None, *, provider=None):
        if operation not in ('profile', 'watch', 'followings', 'tweets', 'ai_profile'):
            raise ValueError('unapproved_provider_operation')
        provider = provider or ('twitterapi' if operation in ('followings','tweets','ai_profile') else '6551')
        if provider not in ('twitterapi', '6551'):raise ValueError('unapproved_provider')
        # Reuse provider_intent so the existing restore carries the latest fence.
        prefix = 'provider_intent:blocked:'+provider
        account = hashlib.sha256((username or '').casefold().encode()).hexdigest()
        return prefix, prefix+':'+operation+':'+account

    def provider_block(self, operation, username=None, *, states=None, provider=None):
        keys = self.provider_block_keys(operation, username, provider=provider)
        if states is None:
            with self.connect() as db:
                states = {r['key']: json.loads(r['value']) for r in db.execute('SELECT key,value FROM state WHERE key IN (?,?)', keys)}
        for key in keys:
            value = states.get(key)
            if value is not None:
                if not isinstance(value, dict) or value.get('state') not in ('blocked', 'released') or value.get('code') not in ('provider_http_400','provider_http_402','provider_http_404'):
                    raise ValueError('invalid_provider_block')
                if value['state'] == 'blocked':
                    return value
        return None

    def block_provider(self, operation, username, code, intent, *, provider_wide=False, now=None, provider=None):
        keys = self.provider_block_keys(operation, username, provider=provider)
        if (provider_wide and (not keys[0].endswith(':twitterapi') or code != 'provider_http_402')
                or not provider_wide and code not in ('provider_http_400', 'provider_http_404')):
            raise ValueError('invalid_provider_block_scope')
        now = time.time() if now is None else now
        key = keys[0 if provider_wide else 1]
        with self.connect(True) as db:
            saved = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
            block = json.loads(saved[0]) if saved else None
            if not block or block['state'] != 'blocked':
                block = {'block_id': str(uuid.uuid4()), 'state': 'blocked', 'code': code,
                         'operation': operation, 'blocked_at': now, 'provider_wide': provider_wide}
                db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(block)))
                self.audit(db, 'provider', 'provider.block', key, now, json.dumps({'block_id': block['block_id'], 'code': code}))
            db.execute('UPDATE state SET value=? WHERE key=?', (json.dumps(None), intent))
        return block

    @staticmethod
    def _release_provider_block(db, key, block, actor, reason, now):
        released = dict(block, state='released', released_at=now, released_by=actor, release_reason=reason)
        db.execute('UPDATE state SET value=? WHERE key=?', (json.dumps(released), key))
        Store.audit(db, actor, 'provider.resume', key, now, json.dumps({'block_id': block['block_id'], 'code': block['code'], 'reason': reason}))

    def resume_provider(self, operation, username=None, *, expected_block_id, actor, reason, now=None, provider=None):
        """Explicit operator action with a block-ID check; never called by a loop."""
        if not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', actor) or not isinstance(reason, str) or not re.fullmatch(r'[a-z0-9_]{1,80}', reason):
            raise ValueError('provider_resume_requires_actor_and_reason')
        now = time.time() if now is None else now
        with self.connect(True) as db:
            for key in self.provider_block_keys(operation, username, provider=provider):
                saved = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
                block = json.loads(saved[0]) if saved else None
                if block and block.get('block_id') == expected_block_id:
                    if block['state'] == 'released':
                        return False
                    self._release_provider_block(db, key, block, actor, reason, now)
                    job = 'poll' if block['operation'] == 'followings' else 'profile'
                    if block['operation'] not in ('watch','tweets','ai_profile'):
                        where = '' if block['provider_wide'] else ' AND username=?'
                        values = (block['code'],) if block['provider_wide'] else (block['code'], username)
                        db.execute(f'UPDATE hunters SET {job}_error=NULL,next_{job}_at=0 WHERE {job}_error=?'+where, values)
                    return True
            raise Conflict('provider_block_changed')

    def set_state(self, key, value):
        if key.startswith(LEGACY_DIRECTORY_PREFIX):
            raise ValueError('legacy_private_state_requires_takeover')
        with self.connect(True) as db:
            previous = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone() if key == 'watch_error' else None
            old = json.loads(previous[0]) if previous else None
            db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
            if key == 'watch_error':
                if old != value:
                    row = db.execute("SELECT value FROM state WHERE key='watch_error_history'").fetchone()
                    history = json.loads(row[0]) if row else []
                    history.append({'at':time.time(), 'from':old, 'to':value})
                    db.execute("INSERT INTO state(key,value) VALUES('watch_error_history',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(history[-512:]),))
                # Remember when the current Watch problem started so health can ignore short transient timeouts.
                if value:
                    db.execute("INSERT OR IGNORE INTO state(key,value) VALUES('watch_error_since',?)", (json.dumps(time.time()),))
                else:
                    db.execute("DELETE FROM state WHERE key='watch_error_since'")

    def states(self):
        """Full table read + parse. Expensive; hot paths must use get_state/get_states/list_states."""
        with self.connect() as db:
            return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM state WHERE key NOT GLOB ?', (LEGACY_DIRECTORY_PREFIX+'*',))}

    def get_state(self, key, default=None):
        """Read and parse a single state row (primary-key lookup)."""
        if key.startswith(LEGACY_DIRECTORY_PREFIX):
            return default
        with self.connect() as db:
            row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def get_states(self, keys):
        """Read only the requested keys; missing keys are absent from the result (like states())."""
        wanted = [k for k in dict.fromkeys(keys) if not k.startswith(LEGACY_DIRECTORY_PREFIX)]
        if not wanted:
            return {}
        result = {}
        with self.connect() as db:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start+500]
                marks = ','.join('?' for _ in chunk)
                for r in db.execute(f'SELECT key,value FROM state WHERE key IN ({marks})', chunk):
                    result[r['key']] = json.loads(r['value'])
        return result

    def list_states(self, prefix):
        """Read all rows whose key starts with prefix (index range scan, no full-table parse)."""
        if not prefix or prefix.startswith(LEGACY_DIRECTORY_PREFIX):
            raise ValueError('invalid_state_prefix')
        with self.connect() as db:
            return {r['key']: json.loads(r['value']) for r in
                    db.execute('SELECT key,value FROM state WHERE substr(key,1,?)=?', (len(prefix), prefix))}

    def prune_expired_caches(self, now=None, *, max_age=CACHE_RETENTION_SECONDS, limit=1000):
        """Delete enrichment caches older than max_age that the code can no longer reuse.

        Only EXPIRING_CACHE_PREFIXES are touched. A row is removed only when its
        timestamp field is a number and strictly older than max_age; unparsable
        or unexpected rows are kept (fail closed).
        """
        now = time.time() if now is None else now
        if max_age < CACHE_REUSE_WINDOW_SECONDS:
            raise ValueError('cache_max_age_below_reuse_window')
        deleted = 0
        with self.connect(True) as db:
            for prefix, field in EXPIRING_CACHE_PREFIXES:
                if prefix.startswith(PROTECTED_STATE_PREFIXES):
                    raise ValueError('protected_state_prefix')
                stale = []
                for r in db.execute('SELECT key,value FROM state WHERE substr(key,1,?)=?', (len(prefix), prefix)):
                    try:
                        value = json.loads(r['value'])
                    except ValueError:
                        continue
                    stamp = value.get(field) if isinstance(value, dict) else None
                    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and now - stamp > max_age:
                        stale.append(r['key'])
                    if len(stale) + deleted >= limit:
                        break
                for key in stale:
                    if key.startswith(PROTECTED_STATE_PREFIXES) or not key.startswith(prefix):
                        raise ValueError('protected_state_prefix')
                    db.execute('DELETE FROM state WHERE key=?', (key,))
                deleted += len(stale)
                if deleted >= limit:
                    break
        return deleted

    @staticmethod
    def legacy_identity_pending(db, identifier):
        row = db.execute('SELECT value FROM state WHERE key=?', (LEGACY_DIRECTORY_PREFIX+'account:'+identifier,)).fetchone()
        if not row:
            return False
        return json.loads(row[0]).get('status') not in ('verified_current','owner_accepted_legacy')

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
        states = self.get_states(('worker_heartbeat', 'wss_state', 'last_pong_at', 'worker_error',
                                  'watch_checked_at', 'watch_error'))
        alive = now - (states.get('worker_heartbeat') or 0) < 15
        return {'worker_alive': alive, 'wss_state': states.get('wss_state', 'stopped') if alive else 'stopped',
                'last_pong_at': states.get('last_pong_at'), 'worker_error': states.get('worker_error'),
                'watch_checked_at': states.get('watch_checked_at'), 'watch_error': states.get('watch_error'),
                'events': events, 'tasks': counts, 'daily_reserved': quotas,
                'window_hours': 72, 'distinct_hunters_required': 2, 'rest_interval_seconds': 3600, 'rest_page_size': 20}
