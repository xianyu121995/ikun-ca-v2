from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import sqlite3
import traceback
from pathlib import Path
from urllib.parse import urlsplit
import time
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect

from .config import Settings
from .parsers import followings, profile, watch_coverage, wss_events
from .providers import ProviderError, Providers
from .store import BudgetExceeded, Conflict, LeaseLost, Store

LOG = logging.getLogger('hunterradar')


def retry_time(failures, now, error=None):
    if isinstance(error, ProviderError) and not error.retryable:
        return None
    if isinstance(error, BudgetExceeded):
        return error.retry_at + random.uniform(1, 5)
    wait = min(300, 5 * 2 ** min(failures, 6)) + random.uniform(0, 3)
    if isinstance(error, ProviderError):
        wait = max(wait, error.retry_after)
    return now+wait


class Engine:
    def __init__(self, settings: Settings, store: Store, providers=None, connector=None):
        self.settings, self.store = settings, store
        self.providers = providers or Providers(settings, store)
        self.connector = connector or connect
        self.stop = asyncio.Event()
        self.semaphore = asyncio.Semaphore(settings.concurrency)
        self.poll_inflight=set()

    async def pause(self, seconds):
        try:
            await asyncio.wait_for(self.stop.wait(), seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self):
        original_store = self.store
        owner = self.store.acquire_worker()
        self.store = original_store.worker_view(owner)
        self.providers.store = self.store
        self.store.recover()
        self.store.set_state('worker_error', None)
        loops = [asyncio.create_task(self.supervise(name, fn)) for name, fn in
                 [('profiles', self.profile_loop), ('rest', self.rest_loop), ('wss', self.wss_loop),
                  ('watch', self.watch_loop), ('outbox', self.outbox_loop), ('heartbeat', self.heartbeat_loop),('retention',self.retention_loop),('ai',self.ai_loop)]]
        try:
            await self.stop.wait()
        finally:
            self.stop.set()
            for task in loops:
                task.cancel()
            await asyncio.gather(*loops, return_exceptions=True)
            try:
                self.store.set_state('wss_state', 'stopped')
                self.store.set_state('worker_heartbeat', 0)
            except LeaseLost:
                pass
            await self.providers.close()
            original_store.release_worker(owner)

    def record_loop_error(self, name, error):
        # Frames contain no arguments/locals; never log raw exception text or credentials.
        frames = traceback.extract_tb(error.__traceback__)
        reasons = {'cross_store_transaction_forbidden', 'hunter_migration_required',
                   'symlinked_database_path_forbidden', 'database_must_be_private_regular_file',
                   'unsafe_hunter_permissions', 'legacy_private_state_requires_takeover'}
        reason = str(error) if isinstance(error, ValueError) and str(error) in reasons else None
        detail = {'loop': name, 'type': type(error).__name__, 'reason': reason,
                  'at': time.time(), 'frames': [f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in frames]}
        self.store.set_state('worker_error_detail', detail)
        LOG.warning('worker_loop_detail %s', json.dumps(detail))

    async def supervise(self, name, fn):
        while not self.stop.is_set():
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except LeaseLost:
                self.stop.set()
                return
            except Exception as error:
                code = name+':'+type(error).__name__
                self.store.set_state('worker_error', code)
                self.record_loop_error(name, error)
                LOG.warning('worker_loop_failed %s', code)
                await self.pause(5)

    async def heartbeat_loop(self):
        successes = 0
        while not self.stop.is_set():
            self.store.renew_worker()
            self.store.set_state('worker_heartbeat', time.time())
            successes += 1
            if successes >= 3:
                # Only a recovered heartbeat may clear its own sticky error.
                with self.store.transaction():
                    error = self.store.states().get('worker_error')
                    if isinstance(error, str) and error.startswith('heartbeat:'):
                        self.store.set_state('worker_error_last_recovery', {'error': error, 'at': time.time()})
                        self.store.set_state('worker_error', None)
            await self.pause(3)

    async def ai_loop(self):
        # AI prefill is optional: failures are logged and retried, never surfaced as worker errors.
        from .ai_prefill import run_pass
        failures = {}
        while not self.stop.is_set():
            try:
                stored = await asyncio.to_thread(run_pass, self.store, failures)
            except LeaseLost:
                raise
            except Exception as error:  # noqa: BLE001
                LOG.warning('hunter_ai_pass_failed %s', type(error).__name__)
                stored = 0
            await self.pause(2 if stored else 15)

    async def retention_loop(self):
        while not self.stop.is_set():
            try:
                result=await asyncio.to_thread(self.store.cleanup)
                self.store.set_state('retention_error',None)
                self.store.set_state('retention_checked_at',time.time())
                if result['deleted']>=500:continue
            except (ValueError,OSError,sqlite3.Error,TimeoutError) as error:
                self.store.set_state('retention_error',type(error).__name__)
            await self.pause(60)

    async def scan_profile(self, row):
        if self.store.provider_block('profile', row['username']):
            return
        try:
            payload = await self.providers.request('profile', row['username'])
            user_id, name, count = profile(payload, row['username'])
            self.store.apply_profile(row, user_id, name, count, time.time())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.store.job_failure(row, 'profile','stable_identity_conflict' if isinstance(error,Conflict) else str(error) if isinstance(error,(ProviderError,BudgetExceeded)) else type(error).__name__,
                                   9999999999 if isinstance(error,Conflict) else retry_time(row['profile_failures'], time.time(), error))

    async def profile_loop(self):
        while not self.stop.is_set():
            states = self.store.states()
            for row in self.store.hunters():
                if row['enabled'] and row['profile_status'] != 'ready' and row['next_profile_at'] <= time.time() and not self.store.provider_block('profile', row['username'], states=states):
                    await self.scan_profile(row)
                if self.stop.is_set():
                    break
            await self.pause(2)

    async def poll(self, row):
        if row['id'] in self.poll_inflight:return
        self.poll_inflight.add(row['id'])
        try:await self._poll(row)
        finally:self.poll_inflight.discard(row['id'])

    async def _poll(self, row):
        async with self.semaphore:
            # Account may have been disabled while queued behind another account.
            current = self.store.hunter(row['id'])
            if not current['enabled'] or current['generation'] != row['generation']:
                return
            if self.store.provider_block('followings', row['username']):
                return
            try:
                payload = await self.providers.request('followings', row['username'])
                result = self.store.apply_poll(row, followings(payload), time.time())
                LOG.info('rest_poll baseline=%s new=%s warning=%s',result.get('baseline'),result['new'],result.get('warning'))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                code = 'stable_identity_conflict' if isinstance(error,Conflict) else str(error) if isinstance(error,(ProviderError,BudgetExceeded)) else type(error).__name__
                self.store.job_failure(row,'poll',code,9999999999 if isinstance(error,Conflict) else retry_time(row['poll_failures'],time.time(),error))

    async def rest_loop(self):
        while not self.stop.is_set():
            states = self.store.states()
            rows = [row for row in self.store.hunters() if row['enabled'] and row['mode'] == 'REST'
                    and row['profile_status'] == 'ready' and row['next_poll_at'] <= time.time()
                    and not self.store.provider_block('followings', row['username'], states=states)]
            # Return exceptions isolates accounts deleted while waiting for a concurrency slot.
            await asyncio.gather(*(self.poll(row) for row in rows), return_exceptions=True)
            await self.pause(1)

    async def watch_loop(self):
        from .watch import synchronize
        previous = None
        while not self.stop.is_set():
            try:
                signature = [(h['id'],h['enabled'],h['mode'],h['deleted_at']) for h in self.store.hunters(include_deleted=True)]
                states = self.store.states()
                if self.settings.external_io_enabled and (signature != previous or time.time()-states.get('watch_checked_at',0)>=300):
                    await synchronize(self)
                    previous = signature
            except (ProviderError, BudgetExceeded, ValueError, TimeoutError) as error:
                if isinstance(error, ValueError):self.record_loop_error('watch', error)
                self.store.set_state('watch_error',str(error) if isinstance(error,ProviderError) else type(error).__name__)
            await self.pause(5)

    async def wss_loop(self):
        failures = 0
        while not self.stop.is_set():
            active = [h for h in self.store.hunters() if h['enabled'] and h['mode']=='WSS' and h['profile_status']=='ready']
            if not self.settings.external_io_enabled:
                self.store.set_state('wss_state', 'external_io_disabled')
                await self.pause(5)
                continue
            if not active or not self.settings.token_6551:
                self.store.set_state('wss_state', 'token_missing' if active else 'idle')
                await self.pause(3)
                continue
            try:
                # A connection attempt is also bounded across restarts.
                self.store.reserve('wss_connect', 1, 1000, 10, time.time())
                self.store.set_state('wss_state', 'connecting')
                await self.consume()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                failures += 1
                self.store.set_state('wss_state', 'reconnecting')
                self.store.set_state('wss_gap_since', time.time())
                self.store.set_state('wss_error', type(error).__name__)
                await self.pause(min(60, retry_time(failures, time.time(), error)-time.time()))

    async def consume(self):
        generation_snapshot=[h for h in self.store.hunters() if h['enabled'] and h['mode']=='WSS' and h['profile_status']=='ready']
        uri = 'wss://ai.6551.io/open/twitter_wss?token='+quote(self.settings.token_6551, safe='')
        async with self.connector(uri, open_timeout=15, close_timeout=5, ping_interval=20, ping_timeout=20, max_size=1_000_000) as socket:
            await socket.send(json.dumps({'jsonrpc':'2.0','id':1,'method':'twitter.subscribe'}))
            ack = json.loads(await asyncio.wait_for(socket.recv(), 15))
            if ack.get('id') != 1 or not isinstance(ack.get('result'), dict) or ack['result'].get('success') is not True:
                raise ProviderError('wss_subscription_not_acknowledged')
            self.store.set_state('wss_state', 'subscribed')
            self.store.set_state('last_pong_at',None)
            # Subscription ACK is not a source heartbeat. Establish only new generations.
            self.store.establish_wss_baseline(generation_snapshot,time.time())
            self.store.set_state('wss_error', None)
            last_pong = time.monotonic()
            next_ping = time.monotonic()+20
            while not self.stop.is_set():
                if time.monotonic()-last_pong > 65:
                    raise ProviderError('wss_application_heartbeat_timeout')
                if time.monotonic() >= next_ping:
                    await socket.send('ping')
                    next_ping = time.monotonic()+20
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                if raw == 'pong' or raw == b'pong':
                    last_pong = time.monotonic()
                    self.store.set_state('last_pong_at', time.time())
                    continue
                try:
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError('invalid_envelope')
                    for event in wss_events(payload, time.time()):
                        origin=next((h for h in generation_snapshot if h['username']==event.hunter),None)
                        if origin:self.store.ingest_wss(event,generation=origin['generation'])
                except (ValueError, TypeError, KeyError,Conflict):
                    self.store.set_state('last_rejected_event_at', time.time())
                if not any(h['enabled'] and h['mode']=='WSS' for h in self.store.hunters()):
                    return
                if any(h['enabled'] and h['mode']=='WSS' and not h['baseline_ready'] for h in self.store.hunters()):return

    def accept_v2_receipt(self, task, payload):
        receipt=payload.get('data') if isinstance(payload,dict) else None
        event_id=task.get('event_id')
        if not isinstance(receipt,dict) or receipt.get('event_id')!=event_id:
            return False
        project_id=receipt.get('project_id','')
        if (not isinstance(project_id,str) or not re.fullmatch(r'prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',project_id)
                or not isinstance(receipt.get('receipt_id'),str) or not receipt['receipt_id']
                or not isinstance(receipt.get('duplicate'),bool) or receipt.get('command_id')!=task.get('command_id')
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)',str(receipt.get('accepted_at','')))
                or task.get('project_id') not in (None,project_id)):
            return False
        try:
            from datetime import datetime
            datetime.fromisoformat(receipt['accepted_at'].replace('Z','+00:00'))
        except ValueError:return False
        clean={key:receipt[key] for key in ('event_id','command_id','project_id','receipt_id','accepted_at','duplicate')}
        self.store.finish_task(task['id'],'delivered',receipt=receipt['receipt_id'],now=time.time(),canonical=project_id,receipt_data=clean)
        return True

    async def deliver_v2(self, task):
        if not task.get('event_id') or not task.get('command_id'):
            self.store.finish_task(task['id'],'failed',code='legacy_confirmation_protocol_review_required')
            return
        # Reconcile FIRST, including after an ambiguous POST/crash; never invent success.
        parsed=urlsplit(self.settings.project_url)
        receipt_url=f'{parsed.scheme}://{parsed.netloc}/internal/v1/receipts/hunter/'+task['event_id']
        headers={'Authorization':'Bearer '+self.settings.project_token,'Idempotency-Key':task['idempotency_key'],
                 'Content-Type':'application/json'}
        try:
            existing=await self.providers.client.get(receipt_url,headers=headers,timeout=5,follow_redirects=False)
            if existing.status_code==200:
                if self.accept_v2_receipt(task,existing.json()):
                    return
                self.store.finish_task(task['id'],'unknown',code='receiver_receipt_requires_reconciliation',retry_at=time.time()+300)
                return
            if existing.status_code!=404:
                status='failed' if existing.status_code in (401,403) else 'unknown'
                self.store.finish_task(task['id'],status,code='receiver_reconcile_http_'+str(existing.status_code),retry_at=time.time()+300)
                return
            if task.get('posted'):
                self.store.finish_task(task['id'],'unknown',code='posted_event_receipt_not_found',retry_at=time.time()+300)
                return
            # Mark before IO; crash/ambiguous failure can only reconcile, never blind repost.
            with self.store.connect(True) as db:
                db.execute('UPDATE task_outbox SET posted=1 WHERE id=?',(task['id'],))
            response=await self.providers.client.post(self.settings.project_url,content=task['body'].encode(),
                                                       headers=headers,timeout=5,follow_redirects=False)
            if response.status_code in (200,201,202) and self.accept_v2_receipt(task,response.json()):
                return
            if response.status_code in (400,401,403,409,422):
                self.store.finish_task(task['id'],'failed',code='receiver_http_'+str(response.status_code))
            else:
                self.store.finish_task(task['id'],'unknown',code='receiver_reconciliation_required',retry_at=time.time()+60)
        except (httpx.HTTPError,ValueError):
            self.store.finish_task(task['id'],'unknown',code='receiver_reconciliation_required',retry_at=time.time()+60)

    async def deliver(self, task):
        if self.settings.delivery_protocol=='v2-event':
            await self.deliver_v2(task)
            return

        body = task['body'].encode()
        issued = str(int(time.time()))
        key = task['idempotency_key']
        signature = hmac.new(self.settings.project_secret.encode(), issued.encode()+b'\n'+key.encode()+b'\n'+body, hashlib.sha256).hexdigest()
        headers = {'Content-Type':'application/json', 'Idempotency-Key':key,
                   'X-HunterRadar-Timestamp':issued, 'X-HunterRadar-Signature':signature}
        code, retry = 'receiver_transport_error', True
        try:
            response = await self.providers.client.post(self.settings.project_url, content=body, headers=headers,
                                                        timeout=self.settings.timeout, follow_redirects=False)
            if response.status_code in (200, 201, 202):
                receipt = response.json()
                if (isinstance(receipt, dict) and receipt.get('accepted') is True and receipt.get('command_id') == task['id']
                        and isinstance(receipt.get('task_id'), str) and 0 < len(receipt['task_id']) <= 200):
                    self.store.finish_task(task['id'], 'delivered', receipt=receipt['task_id'], now=time.time())
                    return
                code, retry = 'receiver_invalid_receipt', False
            else:
                code = 'receiver_http_'+str(response.status_code)
                retry = response.status_code == 429 or response.status_code >= 500
        except (httpx.HTTPError, ValueError):
            pass
        attempts = task['attempts']
        # Idempotent command persists across ambiguous failures. Stop after 10 attempts for operator review.
        status = 'pending' if retry and attempts < 10 else 'failed'
        self.store.finish_task(task['id'], status, code=code,
                               retry_at=time.time()+min(3600, 5*2**min(attempts, 10)))

    async def outbox_loop(self):
        while not self.stop.is_set():
            if self.settings.project_url and (self.settings.project_delivery_enabled if self.settings.delivery_protocol=='v2-event' else self.settings.external_io_enabled):
                task = self.store.claim_task(time.time())
                if task:
                    await self.deliver(task)
                    continue
            await self.pause(2)
