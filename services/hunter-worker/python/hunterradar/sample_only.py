"""Reviewed, one-shot two-Hunter sample. Formal external-IO gates stay closed.

No source is contacted by validation. Running needs pinned local root artifacts,
an offline Hunter writer window and a fresh external Alpha guard. No Watch writer,
outbox delivery, full-monitor loops, env enable flag, or automatic retry exists.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import logging
from pathlib import Path
import re
import signal
import time
import uuid

from .config import Settings, read_env
from .engine import Engine, connect
from .parsers import handle, profile
from .providers import Providers, ProviderError
from .store import Store
from .takeover import EXECUTION, canonical, digest, exact, instant, private_file, read_json, read_private, sha, stable, unique_object

PROTOCOL = 'hunter-sample-only-v1'
STATE_KEY = 'hunter_sample:' + EXECUTION
MAX_SECONDS = 300
WATCH_AUDIT_MAX_AGE = 60
LIMITS = {'profile:WSS': 1, 'profile:REST': 1, 'watch': 1, 'followings': 1, 'wss_connect': 1}
SOURCE_FILES = ('sample_only.py', 'providers.py', 'engine.py', 'store.py', 'config.py', 'parsers.py', 'migration.py', 'takeover.py', 'retention.py')


class SampleBlocked(ValueError):
    pass


def block(code):
    raise SampleBlocked(code)


def source_fingerprint():
    return digest({name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCE_FILES})


def git_sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        block('invalid_review_sha')


def read_guard(path):
    path = private_file(path)
    if path.stat().st_size > 16384:
        block('alpha_guard_too_large')
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


class Permit:
    def __init__(self, store, manifest, manifest_sha256, gates, gates_sha256, alpha_guard,
                 tracking_evidence, alpha_evidence, *, clock=time.time, monotonic=time.monotonic):
        self.store, self.manifest, self.gates = store, manifest, gates
        self.manifest_sha256, self.gates_sha256, self.alpha_guard = manifest_sha256, gates_sha256, alpha_guard
        self.clock, self.monotonic = clock, monotonic
        self.started_wall, self.started_mono = clock(), monotonic()
        self.cancelled = False
        exact(manifest, ('protocol', 'execution_id', 'run_id', 'not_before', 'deadline', 'hunters', 'excluded_accounts'))
        exact(gates, ('protocol', 'execution_id', 'run_id', 'manifest_sha256', 'sample_source_sha256', 'root_review_sha',
                      'hunter_import_package_sha256', 'hunter_import_report_sha256', 'projects_bridge_sha256', 'ownership_sha256',
                      'source_sha256', 'source_stopped', 'tracking_adopt_only_passed', 'tracking_evidence_sha256',
                      'alpha_evidence_sha256', 'shared_account_new_tweet_count', 'shared_account_watch_total',
                      'shared_account_count_checked_at', 'alpha_baseline_reconnect_count'))
        try:
            run_id = str(uuid.UUID(manifest['run_id'], version=4))
        except (ValueError, TypeError, AttributeError):
            block('invalid_sample_run_id')
        if (manifest['protocol'] != PROTOCOL or manifest['execution_id'] != EXECUTION or run_id != manifest['run_id']
                or gates['protocol'] != 'hunter-sample-gates-v2' or gates['execution_id'] != EXECUTION
                or gates['run_id'] != run_id or gates['manifest_sha256'] != manifest_sha256
                or gates['sample_source_sha256'] != source_fingerprint()):
            block('sample_artifact_binding_mismatch')
        for field in ('manifest_sha256', 'sample_source_sha256', 'hunter_import_package_sha256', 'hunter_import_report_sha256',
                      'projects_bridge_sha256', 'ownership_sha256', 'source_sha256', 'tracking_evidence_sha256', 'alpha_evidence_sha256'):
            sha(gates[field])
        git_sha(gates['root_review_sha'])
        self.run_id = run_id
        self.not_before = instant(manifest['not_before']) / 1e6
        self.deadline = instant(manifest['deadline']) / 1e6
        if not 0 < self.deadline - self.not_before <= MAX_SECONDS:
            block('sample_window_exceeds_300_seconds')
        if (gates['source_stopped'] is not True or gates['tracking_adopt_only_passed'] is not True
                or type(gates['shared_account_new_tweet_count']) is not int
                or not 0 <= gates['shared_account_new_tweet_count'] <= 600
                or type(gates['shared_account_watch_total']) is not int
                or gates['shared_account_watch_total'] < gates['shared_account_new_tweet_count']
                or type(gates['alpha_baseline_reconnect_count']) is not int or gates['alpha_baseline_reconnect_count'] < 0):
            block('sample_prerequisites_not_passed')
        self.check_watch_audit_freshness()
        self.accounts = {}
        if not isinstance(manifest['hunters'], list) or len(manifest['hunters']) != 2:
            block('exactly_two_hunters_required')
        for row in manifest['hunters']:
            exact(row, ('account_id', 'x_user_id', 'x_handle', 'mode', 'generation', 'revision', 'watch_entry_sha256'))
            stable(row['x_user_id'])
            if row['x_handle'] != handle(row['x_handle']) or row['mode'] not in ('WSS', 'REST'):
                block('invalid_sample_account')
            if row['mode'] in self.accounts or type(row['generation']) is not int or row['generation'] < 1 or type(row['revision']) is not int or row['revision'] < 1:
                block('ambiguous_sample_account')
            if row['mode'] == 'WSS':
                sha(row['watch_entry_sha256'])
            elif row['watch_entry_sha256'] is not None:
                block('rest_watch_proof_forbidden')
            self.accounts[row['mode']] = dict(row)
        if len({a['x_user_id'] for a in self.accounts.values()}) != 2 or len({a['x_handle'] for a in self.accounts.values()}) != 2 or len({a['account_id'] for a in self.accounts.values()}) != 2:
            block('duplicate_sample_identity')
        excluded = manifest['excluded_accounts']
        if not isinstance(excluded, list) or not 1 <= len(excluded) <= 600:
            block('current_alpha_exclusions_required')
        for row in excluded:
            exact(row, ('x_user_id', 'x_handle'))
            name = handle(row['x_handle'])
            if row['x_handle'] != name:
                block('sample_exclusions_must_be_canonical')
            if row['x_user_id'] is not None:
                stable(row['x_user_id'])
            if any(a['x_handle'] == name or a['x_user_id'] == row['x_user_id'] for a in self.accounts.values()):
                block('sample_alpha_ownership_conflict')
        for path, kind, field in ((tracking_evidence, 'tracking_adopt_only', 'tracking_evidence_sha256'),
                                  (alpha_evidence, 'alpha_protection', 'alpha_evidence_sha256')):
            evidence = read_json(path, gates[field])
            exact(evidence, ('protocol', 'execution_id', 'kind', 'passed', 'reviewed_sha', 'checked_at'))
            if (evidence['protocol'] != 'hunter-sample-prerequisite-v1' or evidence['execution_id'] != EXECUTION
                    or evidence['kind'] != kind or evidence['passed'] is not True
                    or not 0 <= self.now() - instant(evidence['checked_at']) / 1e6 <= 3600):
                block('sample_prerequisite_evidence_invalid')
            git_sha(evidence['reviewed_sha'])
        self.expected = {}
        self.wss_events = 0; self.rest_events = 0
        self.verify_import()
        self.check()

    def now(self):
        return max(self.clock(), self.started_wall + self.monotonic() - self.started_mono)

    def check_watch_audit_freshness(self):
        if not 0 <= self.now() - instant(self.gates['shared_account_count_checked_at']) / 1e6 <= WATCH_AUDIT_MAX_AGE:
            block('sample_watch_audit_stale_reconcile')

    def verify_watch(self, payload):
        self.check(); self.check_watch_audit_freshness()
        # Only explicit complete-list envelopes are supported. Unknown paging or
        # partial-result metadata is not silently interpreted as completeness.
        envelope_keys = {'data','success','status','message','msg','request_id','total'}
        if not isinstance(payload, dict) or set(payload) - envelope_keys or 'data' not in payload:
            block('sample_watch_completeness_unknown')
        if 'success' in payload and payload['success'] is not True:
            block('sample_watch_snapshot_invalid')
        data = payload['data']; totals = []
        if 'total' in payload: totals.append(payload['total'])
        if isinstance(data, list):
            rows = data  # Full entry count must also match the fresh root audit.
        elif isinstance(data, dict) and set(data) in ({'list','total'},{'items','total'}):
            rows = data['list'] if 'list' in data else data['items']
            totals.append(data['total'])
        else:
            block('sample_watch_completeness_unknown')
        if not isinstance(rows, list) or any(type(total) is not int or total != len(rows) for total in totals):
            block('sample_watch_snapshot_incomplete')
        if len(rows) != self.gates['shared_account_watch_total']:
            block('sample_watch_count_drift_reconcile')
        identifiers = set(); names = set(); selected = None; used = 0
        account = self.accounts['WSS']
        for row in rows:
            if not isinstance(row, dict) or type(row.get('newTweetBol')) is not bool:
                block('sample_watch_row_invalid')
            watch_id = row.get('id')
            if (type(watch_id) not in (str,int) or (type(watch_id) is int and watch_id < 0)
                    or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', str(watch_id))):
                block('sample_watch_identity_invalid')
            try:
                name = handle(row.get('twAccount', row.get('username')))
                if 'twAccount' in row and 'username' in row and handle(row['username']) != name:
                    block('sample_watch_identity_conflict')
            except (TypeError, ValueError) as error:
                if isinstance(error, SampleBlocked): raise
                block('sample_watch_identity_invalid')
            if str(watch_id) in identifiers or name in names:
                block('sample_duplicate_watch_identity')
            identifiers.add(str(watch_id)); names.add(name)
            used += int(row['newTweetBol'])  # Includes Alpha/unknown, paused or not.
            if name == account['x_handle']: selected = row
        if used > 600:
            block('sample_shared_watch_quota_exceeded')
        if used != self.gates['shared_account_new_tweet_count']:
            block('sample_watch_count_drift_reconcile')
        if selected is None:
            block('sample_existing_watch_proof_changed')
        states = [selected.get(key) for key in ('isPaused','isSuspended','isBlacked')]
        if any(type(value) is not bool for value in states):
            block('sample_watch_status_unknown')
        if any(states):
            block('sample_watch_inactive')
        if selected.get('newFlwBol') is not True or digest(selected) != account['watch_entry_sha256']:
            block('sample_existing_watch_proof_changed')
        return selected  # Keep the original row/flags/group/hash; no mutation.

    def verify_import(self):
        if self.store.inspect() != 5:
            block('sample_requires_migrated_schema5')
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM hunter_takeover_runs WHERE package_sha256=?', (self.gates['hunter_import_package_sha256'],)).fetchone()
            if (not row or row['execution_id'] != EXECUTION or row['source_sha256'] != self.gates['source_sha256'] or row['ownership_sha256'] != self.gates['ownership_sha256']
                    or row['projects_sha256'] != self.gates['projects_bridge_sha256']
                    or hashlib.sha256(row['report_json'].encode()).hexdigest() != self.gates['hunter_import_report_sha256']
                    or json.loads(row['report_json']).get('source_stopped') is not True):
                block('sample_import_receipt_not_verified')
            for account in self.accounts.values():
                current = db.execute('SELECT * FROM hunters WHERE id=?', (account['account_id'],)).fetchone()
                if not current or (current['user_id'], current['username'], current['mode'], current['generation'], current['version']) != (account['x_user_id'], account['x_handle'], account['mode'], account['generation'], account['revision']):
                    block('sample_account_revision_or_identity_changed')
                if not current['enabled'] or current['deleted_at'] is not None or current['profile_status'] != 'ready':
                    block('sample_account_not_ready')
                if account['mode'] == 'REST':
                    proof = db.execute('SELECT * FROM hunter_takeover_baselines WHERE hunter_id=?', (current['id'],)).fetchone()
                    if not current['baseline_ready'] or not proof or not proof['ready_proven'] or proof['source_sha256'] != row['source_sha256']:
                        block('sample_rest_baseline_not_proven')
                    if max(current['next_poll_at'], (current['last_poll_at'] or 0) + 3600) > self.now():
                        block('sample_rest_hourly_poll_not_due')
                self.expected[current['id']] = dict(current)

    def check(self):
        if self.cancelled:
            block('sample_stopped')
        now = self.now()
        if now < self.not_before:
            block('sample_not_before')
        if now >= self.deadline:
            block('sample_deadline_reached')
        guard = read_guard(self.alpha_guard)
        exact(guard, ('protocol', 'execution_id', 'run_id', 'observed_at', 'last_pong_at', 'healthy', 'reconnect_count', 'exclusions_sha256'))
        if (guard['protocol'] != 'hunter-sample-alpha-guard-v1' or guard['execution_id'] != EXECUTION or guard['run_id'] != self.run_id
                or guard['healthy'] is not True or type(guard['reconnect_count']) is not int
                or guard['reconnect_count'] != self.gates['alpha_baseline_reconnect_count']
                or guard['exclusions_sha256'] != digest(self.manifest['excluded_accounts'])
                or not -1 <= now - instant(guard['observed_at']) / 1e6 <= 10
                or not -1 <= now - instant(guard['last_pong_at']) / 1e6 <= 45):
            block('sample_alpha_guard_failed')

    def account(self, identifier):
        self.check()
        expected = self.expected.get(identifier)
        if not expected:
            block('sample_identity_not_allowed')
        current = self.store.hunter(identifier)
        keys = ('user_id', 'username', 'mode', 'generation', 'version', 'enabled', 'deleted_at')
        if any(current[k] != expected[k] for k in keys):
            block('sample_account_changed')
        return current

    def refresh(self, identifier, revision_delta=0):
        current = self.store.hunter(identifier); old = self.expected[identifier]
        if (any(current[k] != old[k] for k in ('user_id','username','mode','generation','enabled','deleted_at'))
                or current['version'] != old['version'] + revision_delta):
            block('sample_account_changed')
        self.expected[identifier] = current

    def claim_run(self):
        self.check()
        with self.store.transaction() as db:
            if db.execute('SELECT 1 FROM state WHERE key=?', (STATE_KEY,)).fetchone():
                block('sample_already_claimed_reconcile_required')
            data = dict(protocol=PROTOCOL, run_id=self.run_id, manifest_sha256=self.manifest_sha256,
                        gates_sha256=self.gates_sha256, status='running', requests={}, started_at=self.now(), deadline=self.deadline)
            db.execute('INSERT INTO state(key,value) VALUES(?,?)', (STATE_KEY, canonical(data)))

    def claim(self, operation, username=None):
        self.check()
        if operation == 'profile':
            account = next((a for a in self.accounts.values() if a['x_handle'] == username), None)
            if not account:
                block('sample_identity_not_allowed')
            self.account(account['account_id']); key = 'profile:' + account['mode']
        elif operation == 'followings':
            account = self.accounts['REST']
            if username != account['x_handle']:
                block('sample_identity_not_allowed')
            current = self.account(account['account_id'])
            if max(current['next_poll_at'], (current['last_poll_at'] or 0) + 3600) > self.now():
                block('sample_rest_hourly_poll_not_due')
            key = operation
        elif operation in ('watch', 'wss_connect') and username is None:
            for a in self.accounts.values():
                self.account(a['account_id'])
            key = operation
        else:
            block('sample_operation_not_allowed')
        with self.store.transaction() as db:
            row = db.execute('SELECT value FROM state WHERE key=?', (STATE_KEY,)).fetchone()
            if not row:
                block('sample_not_claimed')
            data = json.loads(row[0])
            if data['status'] != 'running' or data['run_id'] != self.run_id or data['requests'].get(key, 0) >= LIMITS[key]:
                block('sample_request_budget_exhausted')
            data['requests'][key] = data['requests'].get(key, 0) + 1
            db.execute('UPDATE state SET value=? WHERE key=?', (canonical(data), STATE_KEY))

    def finish(self, code):
        with self.store.transaction() as db:
            data = json.loads(db.execute('SELECT value FROM state WHERE key=?', (STATE_KEY,)).fetchone()[0])
            data.update(status='closed', code=code, finished_at=self.now(), wss_follow_events=self.wss_events, rest_follow_events=self.rest_events,
                        watch_writes=0, outbox_deliveries=0, source_delivery_verified=self.wss_events > 0 and self.rest_events > 0)
            db.execute('UPDATE state SET value=? WHERE key=?', (canonical(data), STATE_KEY))
            return data


class ScopedStore:
    """Restrict existing Engine helpers to exactly the reviewed generations."""
    def __init__(self, base, permit):
        self.base, self.permit = base, permit

    def __getattr__(self, key):
        return getattr(self.base, key)

    def hunters(self):
        return [self.permit.account(a['account_id']) for a in self.permit.accounts.values()]

    def hunter(self, identifier):
        return self.permit.account(identifier)

    def set_state(self, key, value):
        if not key.startswith(('provider_intent:', 'cooldown:')):
            key = 'sample:' + self.permit.run_id + ':' + key
        return self.base.set_state(key, value)

    def states(self):
        states = self.base.states(); prefix = 'sample:' + self.permit.run_id + ':'
        return {k: v for k, v in states.items() if k.startswith(('provider_intent:', 'cooldown:'))} | {k[len(prefix):]: v for k, v in states.items() if k.startswith(prefix)}

    def establish_wss_baseline(self, rows, now):
        allowed = self.hunter(self.permit.accounts['WSS']['account_id'])
        if len(rows) != 1 or rows[0]['id'] != allowed['id']:
            block('sample_baseline_scope_conflict')
        self.base.establish_wss_baseline([allowed], now)
        self.permit.refresh(allowed['id'])

    def ingest_wss(self, event, *, generation=None):
        row = self.hunter(self.permit.accounts['WSS']['account_id'])
        if event.hunter != row['username'] or generation != row['generation']:
            block('sample_event_scope_conflict')
        result = self.base.ingest_wss(event, generation=generation)
        self.permit.wss_events += int(result)
        return result

    def apply_poll(self, row, targets, now):
        current = self.hunter(self.permit.accounts['REST']['account_id'])
        if row['id'] != current['id'] or row['generation'] != current['generation']:
            block('sample_poll_scope_conflict')
        result = self.base.apply_poll(current, targets, now)
        self.permit.rest_events += result['new']; self.permit.refresh(current['id'])
        return result

    def coverage(self, usernames, now):
        current = self.hunter(self.permit.accounts['WSS']['account_id'])
        if usernames != {current['username']}:
            block('sample_watch_coverage_scope_conflict')
        with self.base.transaction() as db:
            db.execute('UPDATE hunters SET watch_covered=1 WHERE id=? AND generation=?', (current['id'], current['generation']))
        self.set_state('watch_checked_at', now)


class SampleProviders(Providers):
    def __init__(self, settings, store, permit, client=None):
        if settings.external_io_enabled or not settings.require_external_io_disabled or not settings.v2_mode:
            block('sample_requires_formal_gate_closed')
        for name in ('httpx', 'httpcore', 'websockets'):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        super().__init__(settings, store, client)
        self.permit = permit

    async def request(self, operation, username=None):
        remaining = self.permit.deadline - self.permit.now()
        payload = await asyncio.wait_for(super()._read_only(operation, username, sample_permit=self.permit), timeout=min(self.settings.timeout, remaining))
        if operation == 'followings':
            # Current official UserProfileSnake -> frozen parser's explicit DTO.
            # No second request, pagination, guessed identity, or raw persistence.
            rows = payload.get('followings')
            if not isinstance(rows, list) or len(rows) > 20:
                block('sample_followings_shape_invalid')
            normalized = []
            for row in rows:
                if not isinstance(row, dict):
                    block('sample_followings_shape_invalid')
                modern, previous = row.get('screen_name'), row.get('userName')
                if modern is not None and previous is not None and handle(modern) != handle(previous):
                    block('sample_followings_handle_conflict')
                normalized.append({'id': stable(row.get('id')), 'userName': handle(modern if modern is not None else previous),
                                   'name': row.get('name') or '', 'description': row.get('description') or '',
                                   'unavailable': row.get('unavailable', False)})
            return {'followings': normalized}
        return payload


class FilteredSocket:
    def __init__(self, socket, permit):
        self.socket, self.permit, self.frames = socket, permit, 0

    async def send(self, value):
        self.permit.check()
        if value != 'ping' and json.loads(value) != {'jsonrpc': '2.0', 'id': 1, 'method': 'twitter.subscribe'}:
            block('sample_socket_operation_forbidden')
        await self.socket.send(value)

    async def recv(self):
        while True:
            self.permit.check()
            raw = await self.socket.recv(); self.frames += 1
            if self.frames > 1000:
                block('sample_frame_limit')
            if raw in ('pong', b'pong'):
                return raw
            try:
                payload = json.loads(raw, object_pairs_hook=unique_object)
                if not isinstance(payload, dict):
                    continue
                if payload.get('id') == 1 and isinstance(payload.get('result'), dict) and 'method' not in payload and 'params' not in payload:
                    return canonical(payload)
                params = payload.get('params')
                if payload.get('method') != 'twitter.event' or not isinstance(params, dict):
                    continue
                account = self.permit.accounts['WSS']
                if handle(params.get('twAccount')) != account['x_handle'] or params.get('eventType') != 'NEW_FOLLOWER':
                    continue  # Foreign/Alpha content never reaches Engine/parser/log/store.
                self.permit.account(account['account_id'])
                if params.get('twId') is not None and str(params['twId']) != account['x_user_id']:
                    continue
                return canonical(payload)
            except SampleBlocked:
                raise
            except (ValueError, TypeError, KeyError, UnicodeError):
                continue


class SampleConnector:
    def __init__(self, permit, connector=connect):
        self.permit, self.connector = permit, connector

    @asynccontextmanager
    async def __call__(self, uri, **options):
        if not uri.startswith('wss://ai.6551.io/open/twitter_wss?token='):
            block('sample_socket_endpoint_forbidden')
        self.permit.claim('wss_connect')
        options['open_timeout'] = min(15, self.permit.deadline - self.permit.now())
        async with self.connector(uri, **options) as socket:
            yield FilteredSocket(socket, self.permit)


async def run_sample(permit, settings, *, offline_confirmed=False, client=None, connector=connect):
    if not offline_confirmed:
        block('offline_writer_confirmation_required')
    permit.check()
    base = permit.store; owner = base.acquire_worker(); claimed = False; engine = None
    tasks = []
    try:
        permit.store = base.worker_view(owner)
        permit.claim_run(); claimed = True
        scoped = ScopedStore(permit.store, permit)
        provider = SampleProviders(settings, scoped, permit, client)
        engine = Engine(settings, scoped, provider, SampleConnector(permit, connector))

        async def collect():
            for account in permit.accounts.values():
                payload = await provider.request('profile', account['x_handle'])
                identifier, name, followers = profile(payload, account['x_handle'])
                if identifier != account['x_user_id'] or ('WSS' if followers >= 5000 else 'REST') != account['mode']:
                    block('sample_live_profile_identity_or_channel_conflict')
                row = permit.account(account['account_id'])
                if not permit.store.apply_profile(row, identifier, name, followers, permit.now()):
                    block('sample_profile_generation_changed')
                permit.refresh(row['id'], revision_delta=1)
            watch = await provider.request('watch')
            permit.verify_watch(watch)
            account = permit.accounts['WSS']
            # Coverage is local and scoped. Never normalize the remote row/flags/group.
            scoped.coverage({account['x_handle']}, permit.now())
            await engine.poll(permit.account(permit.accounts['REST']['account_id']))
            if permit.account(permit.accounts['REST']['account_id'])['poll_error']:
                block('sample_rest_failed_reconcile_before_retry')
            await engine.consume()  # Existing subscription, ping/pong, parsing and ingest.

        async def watchdog():
            while True:
                permit.check()
                for row in permit.accounts.values():
                    permit.account(row['account_id'])
                await asyncio.sleep(.1)

        tasks = [asyncio.create_task(collect()), asyncio.create_task(watchdog()), asyncio.create_task(engine.heartbeat_loop())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        code = 'sample_stream_closed'
        for task in done:
            error = task.exception()
            if error:
                if isinstance(error, SampleBlocked): code = str(error)
                elif isinstance(error, ProviderError): code = error.code
                else: code = 'sample_transport_or_storage_failed'
        return permit.finish(code)
    except asyncio.CancelledError:
        if claimed: permit.finish('sample_interrupted_reconcile_before_retry')
        raise
    except BaseException:
        if claimed: permit.finish('sample_failed_reconcile_before_retry')
        raise
    finally:
        permit.cancelled = True
        if engine: engine.stop.set()
        for task in tasks: task.cancel()
        try:
            if tasks: await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
            if engine: await asyncio.wait_for(engine.providers.close(), timeout=5)
        finally:
            base.release_worker(owner)


def load_permit(args):
    return Permit(Store(Path(args.database)), read_json(args.manifest, args.manifest_sha256), args.manifest_sha256,
                  read_json(args.gates, args.gates_sha256), args.gates_sha256, args.alpha_guard,
                  args.tracking_evidence, args.alpha_evidence)


def main():
    parser = argparse.ArgumentParser(description='Bounded reviewed two-Hunter sample; formal IO remains disabled')
    parser.add_argument('command', choices=('check', 'run', 'fingerprint'))
    for flag in ('database', 'manifest', 'manifest-sha256', 'gates', 'gates-sha256', 'alpha-guard', 'tracking-evidence', 'alpha-evidence', 'secrets-file'):
        parser.add_argument('--' + flag)
    parser.add_argument('--offline-confirmed', action='store_true')
    args = parser.parse_args()
    for name in ('httpx', 'httpcore', 'websockets'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        if args.command == 'fingerprint':
            print(canonical({'sample_source_sha256': source_fingerprint()})); return
        if not all(getattr(args, k) for k in ('database', 'manifest', 'manifest_sha256', 'gates', 'gates_sha256', 'alpha_guard', 'tracking_evidence', 'alpha_evidence')):
            block('sample_review_artifacts_required')
        permit = load_permit(args)
        if args.command == 'check':
            print(canonical({'state': 'local_gates_validated_no_connection', 'network_requests': 0})); return
        if not args.offline_confirmed:
            block('offline_writer_confirmation_required')
        if not args.secrets_file:
            block('sample_private_secrets_required')
        values = read_env(private_file(args.secrets_file))
        if not values.get('OPENNEWS_TOKEN') or not values.get('TWITTERAPI_IO_API_KEY'):
            block('sample_credentials_missing')
        settings = Settings(db=permit.store.path, v2_mode=True, external_io_enabled=False, require_external_io_disabled=True,
                            token_6551=values['OPENNEWS_TOKEN'], token_twitterapi=values['TWITTERAPI_IO_API_KEY'], concurrency=1)
        async def execute():
            task = asyncio.create_task(run_sample(permit, settings, offline_confirmed=args.offline_confirmed))
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, task.cancel)
            try: return await task
            finally:
                for sig in (signal.SIGTERM, signal.SIGINT): loop.remove_signal_handler(sig)
        print(canonical(asyncio.run(execute())))
    except asyncio.CancelledError:
        print(canonical({'error': 'sample_interrupted_reconcile_before_retry'})); raise SystemExit(130) from None
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z0-9_]+', str(error)) else 'sample_artifact_or_storage_error'
        print(canonical({'error': code})); raise SystemExit(1) from None


if __name__ == '__main__':
    main()
