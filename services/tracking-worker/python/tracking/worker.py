from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
import uuid
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from .config import Config
from .events import normalize, parse_event
from .remote import OTHER_FLAGS, Remote, RemoteError
from .store import Store
from provider_6551 import wss_auth_delay

log = logging.getLogger("tracking.worker")


class Worker:
    def __init__(self, cfg: Config, store: Store, remote: Remote, ws_connect=connect):
        self.cfg, self.store, self.remote, self.ws_connect = cfg, store, remote, ws_connect
        self.stop = asyncio.Event()
        self.worker_id = str(uuid.uuid4())
        self._leased = False
        self._last_reconcile = 0
        self.ledger = remote.ledger
        previous=store.runtime()
        if previous.get('heartbeat'):
            self.ledger.mark_gap(previous.get('pong_at') or previous['heartbeat'])
        self._reconnected_at = None
        self._watch_requested=True;self._watch_retry_at=0
        self._subscription_signature=None
        self.ledger.request_watch_check()

    def acquire(self):
        if not self.store.lease(self.worker_id, acquire=True):
            raise RuntimeError("another tracking worker owns this database") from None
        self._leased = True

    def ensure_owner(self):
        if self._leased and not self.store.lease(self.worker_id):
            self.stop.set()
            raise RuntimeError("tracking worker lease lost")

    def release(self):
        if self._leased:
            self.store.lease(self.worker_id, release=True)
            self._leased = False

    def adoptable(self, row):
        return row['handle'] in (self.cfg.adoptable_handles or ()) and row['handle'] not in (self.cfg.shared_watch_ids or {})

    def usable_watch(self, row, watch):
        if self.adoptable(row):
            return watch.get('newTweetBol') is True and not any(watch.get(k) for k in ('isPaused','isSuspended','isBlacked'))
        return self.pure_tweet(watch)

    def owned(self, row, watch):
        if row['handle'] in (self.cfg.shared_watch_ids or {}):
            return False
        if self.adoptable(row):
            return True
        if str(watch.get("id")) == (self.cfg.adopted_watch_ids or {}).get(row["handle"]):
            return True
        return row["claim"] in ("reserved", "owned") and (
            watch.get("remark") == "ikun-ca-v2:tracking" or watch.get("groupName") == self.cfg.watch_group
            or str(watch.get("id")) == (self.cfg.adopted_watch_ids or {}).get(row["handle"])
        )

    @staticmethod
    def pure_tweet(watch):
        return watch.get("newTweetBol") is True and all(watch.get(k) is False for k in OTHER_FLAGS if k != "newTweetQuoteBol")

    def fail(self, row, exc: RemoteError):
        attempts = row["attempts"] + 1
        delay = max(exc.retry_after, min(3600, 60 * 2 ** min(attempts-1, 6)) + random.random())
        self.store.observe(
            row,
            status="blocked" if exc.code in ("ownership_conflict", "remote_not_configured") else "retrying",
            remote_state="unknown",
            error=exc.code,
            attempts=attempts,
            next_retry=time.time() + delay,
        )

    async def reconcile_one(self, row, snapshot):
        watch = snapshot.get(row["handle"])
        if row["handle"] in (self.cfg.shared_watch_ids or {}):
            # Explicit read permission never grants add/update/delete authority.
            running = row["desired"] == "running"
            if running:
                if not watch:
                    raise RemoteError("shared_watch_missing", 300)
                if str(watch.get("id")) != self.cfg.shared_watch_ids[row["handle"]]:
                    raise RemoteError("shared_watch_identity_changed", 300)
                if watch.get("newTweetBol") is not True or any(
                    watch.get(k) for k in ("isPaused", "isSuspended", "isBlacked")
                ):
                    raise RemoteError("shared_watch_not_enabled", 300)
            self.store.observe(
                row, remote_state="active" if running else "absent",
                observed_at=time.time(), claim="none",
                status="running" if running else row["desired"],
                error=None, attempts=0, next_retry=0,
                baseline_ready=1, coverage="possible_gap",
            )
            # Stopping/removing only detaches locally; no paid REST backfill either.
            return snapshot
        if watch and not self.owned(row, watch):
            raise RemoteError("ownership_conflict", 300)
        desired_running = row["desired"] == "running"
        if watch and self.adoptable(row):
            if self.store.adopt_watch(row, watch.get('id')):
                log.info('watch_adopted handle=%s watch_id=%s flags_preserved=true',row['handle'],watch.get('id'))
                row = {**row, 'claim':'owned'}
            if desired_running and not self.usable_watch(row,watch):
                raise RemoteError('adopted_watch_not_enabled',300)
        if watch and not self.adoptable(row) and not self.pure_tweet(watch):
            # An external edit is never silently overwritten, even in our namespace.
            raise RemoteError("remote_flags_conflict", 300)
        if desired_running and not watch:
            if len(snapshot) >= self.cfg.max_watch_slots:
                raise RemoteError("quota_exhausted", 60)
            if not self.store.observe(row, claim="reserved", status="starting"):
                return snapshot
            row = {**row, "claim": "reserved"}
            mutation = self.remote.add
        elif not desired_running and watch:
            mutation = self.remote.delete
        else:
            mutation = None
        if mutation:
            self.ensure_owner()
            from .commands import executing

            if not executing(self.store, row):
                return snapshot
            error = None
            try:
                await mutation(row["handle"])
            except RemoteError as exc:
                error = exc
            # A success response, timeout, or error is never the authoritative final state.
            snapshot = await self.remote.watches()
            self.ensure_owner()
            watch = snapshot.get(row["handle"])
            if watch and not self.owned(row, watch):
                raise RemoteError("ownership_conflict", 300)
            matches = (bool(watch) and self.usable_watch(row,watch)) if desired_running else watch is None
            if not matches:
                raise error or RemoteError("remote_verification_failed")
        state = "active" if watch else "absent"
        claim = "owned" if watch else row["claim"]
        updated = self.store.observe(
            row,
            remote_state=state,
            observed_at=time.time(),
            claim=claim,
            status="running" if desired_running else row["desired"],
            error=None,
            attempts=0,
            next_retry=0,
            **({'baseline_ready':1,'coverage':'possible_gap'} if self.adoptable(row) and desired_running else {}),
        )
        if updated and desired_running and not self.adoptable(row):
            await self.backfill({**row, "remote_state": state, "claim": claim})
        return snapshot

    async def backfill(self, row):
        if row['desired']!='running':return
        if not row['baseline_ready'] and not row['last_backfill']:self.ledger.initial(row)
        for job in self.ledger.jobs(row['subscription_id']):
            if job['generation']!=row['generation']:
                self.ledger.discard(job['key']);continue
            try:
                items=await self.remote.tweets(row['handle'],job=job)
                self.ensure_owner()
                tweets=[normalize(item,row['handle'],require_author=True,
                          event_type='REST_USER_TWEETS_NO_RETWEETS') for item in items]
                valid=[t for t in tweets if t and job['from_at']<=t['created_at']<=job['to_at']]
                coverage='possible_gap' if len(items)>=100 or row['coverage']=='possible_gap' else 'bounded_latest_100'
                for tweet in sorted(valid,key=lambda x:x['created_at']):
                    self.store.insert_tweet(row,tweet,'rest_recovery')
                self.store.observe(row,last_backfill=time.time(),coverage=coverage,baseline_ready=1)
            except RemoteError as error:
                # Blocked before transport stays queued; an attempted request is never replayed.
                if not any(x['key']==job['key'] for x in self.ledger.jobs(row['subscription_id'])):
                    self.store.observe(row,last_backfill=time.time(),
                        coverage='possible_gap' if row['coverage']=='possible_gap' else 'recovery_failed')
                if error.code in ('quota_exhausted','daily_budget_exhausted','backfill_daily_limit','provider_busy'):return

    async def process_backfills(self):
        rows=[r for r in self.store.projects() if r['desired']=='running' and
              (r['claim']=='owned' or r['handle'] in (self.cfg.shared_watch_ids or {}))]
        if self._reconnected_at:
            self.ledger.close_gap(self._reconnected_at,rows);self._reconnected_at=None
        for row in rows:
            if self.stop.is_set():break
            await self.backfill(row)

    async def reconcile(self):
        from watch_lock import watch_lock
        async with watch_lock(self.cfg.db_path):
            await self._reconcile_locked()

    async def _reconcile_locked(self):
        self.ensure_owner()
        now = time.time()
        rows = [r for r in self.store.projects(include_removed=True) if r["next_retry"] <= now and not (r["desired"] == "removed" and r["remote_state"] == "absent" and r["status"] == "removed")]
        if not rows:
            return
        try:
            self._last_reconcile = now
            snapshot = await self.remote.watches()
            self._last_reconcile = now
        except RemoteError as exc:
            for row in rows:
                self.fail(row, exc)
            self._watch_requested=True
            self._watch_retry_at=min(r['next_retry'] for r in self.store.projects(include_removed=True)
                                     if r['next_retry']>now)
            return
        self._watch_requested=False;self._watch_retry_at=0
        for row in rows:
            if self.stop.is_set():
                break
            try:
                snapshot = await self.reconcile_one(row, snapshot)
            except RemoteError as exc:
                self.fail(row, exc)
                self._watch_requested=True
                self._watch_retry_at=max(self._watch_retry_at,time.time()+max(60,exc.retry_after))
                # A possibly applied mutation invalidates the prior snapshot.
                try:
                    snapshot = await self.remote.watches()
                except RemoteError as list_exc:
                    for pending in rows[rows.index(row) + 1 :]:
                        self.fail(pending, list_exc)
                    break

    def ingest(self, message, trace=None):
        self.ensure_owner()
        on_drop = trace.drop if trace else None
        event = parse_event(message,on_drop=on_drop)
        if event is None:
            return False
        username, tweet = event
        row = next((r for r in self.store.projects() if r["handle"] == username), None)
        shared = row and row["handle"] in (self.cfg.shared_watch_ids or {})
        if (not row or row["desired"] != "running" or not (row["claim"] == "owned" or shared)
                or row.get('error') in ('ownership_conflict', 'shared_watch_identity_changed')):
            if trace:trace.drop('not_subscribed' if not row else 'not_running_or_owned')
            return False
        # REST control-plane failures never revoke an authorized WSS subscription.
        # insert_tweet still checks revision, local desired state and author identity.
        try:result = self.store.insert_tweet(row,tweet,'wss',on_drop=on_drop)
        except Exception:
            if trace:trace.drop('store_error')
            raise
        if result and trace:trace.accepted()
        return result

    async def session(self, ws, audit=None):
        from wss_audit import WssAudit
        audit = audit or WssAudit('tracking')
        ack, pong = asyncio.Event(), asyncio.Event()

        async def receiver():
            async for raw in ws:
                if raw in ("pong", b"pong"):
                    audit.pong()
                    pong.set()
                    continue
                if raw in ("ping", b"ping"):
                    await ws.send("pong")
                    continue
                try:
                    message = json.loads(raw)
                except (ValueError, TypeError):
                    audit.emit('dropped',reason='invalid_json')
                    continue
                if not isinstance(message, dict):
                    audit.emit('dropped',reason='invalid_envelope')
                    continue
                trace = audit.frame(message)
                if message.get("id") == 1:
                    if message.get("result", {}).get("success") is True:
                        audit.emit('subscribed')
                        self._reconnected_at=time.time()
                        self._watch_requested=True;self._watch_retry_at=0
                        self.ledger.wss_recovered('tracking')
                        ack.set()
                    else:
                        trace.drop('subscription_rejected')
                        raise RemoteError("subscription_rejected")
                elif message.get("error"):
                    trace.drop('provider_stream_error')
                    raise RemoteError("stream_error")
                elif ack.is_set():
                    self.ingest(message,trace)
                else:trace.drop('before_subscription_ack')
            raise RemoteError("stream_closed")

        async def heartbeat():
            try:await asyncio.wait_for(ack.wait(), timeout=self.cfg.heartbeat_timeout)
            except asyncio.TimeoutError:
                audit.emit('dropped',reason='subscription_ack_timeout')
                raise
            while True:
                pong.clear()
                await ws.send("ping")
                try:await asyncio.wait_for(pong.wait(), timeout=self.cfg.heartbeat_timeout)
                except asyncio.TimeoutError:
                    audit.emit('dropped',reason='application_heartbeat_timeout')
                    raise
                self.ensure_owner()
                self.store.runtime(connection="connected", pong_at=time.time(), error=None)
                await asyncio.sleep(self.cfg.heartbeat_seconds)

        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "twitter.subscribe"}))
        tasks = [asyncio.create_task(receiver()), asyncio.create_task(heartbeat())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def streams(self):
        failures = 0
        auth_failures=0
        while not self.stop.is_set():
            start = time.monotonic()
            try:
                self.remote.ready()
                from wss_audit import connection
                self.store.runtime(connection="connecting", pong_at=None, error=None)
                url = "wss://ai.6551.io/open/twitter_wss?" + urlencode({"token": self.cfg.secret("token")})
                async with connection(self.ws_connect(
                    url,
                    open_timeout=15,
                    close_timeout=5,
                    ping_interval=None,
                    max_size=1024 * 1024,
                    max_queue=64,
                ),'tracking') as (ws,audit):
                    await self.session(ws,audit)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.stop.is_set():
                    break
                code = exc.code if isinstance(exc, RemoteError) else "stream_disconnected"
                status=getattr(getattr(exc,'response',None),'status_code',None)
                if status==401:
                    auth_failures+=1;code='wss_auth_rejected'
                    self.ledger.wss_rejected('tracking')
                else:auth_failures=0
                self.ledger.mark_gap(self.store.runtime().get('pong_at') or time.time())
                self.store.runtime(connection="disconnected", pong_at=None, error=code)
                # Logging only the classification avoids leaking a token-bearing handshake URL.
                log.warning("stream disconnected: %s", code)
            failures = 0 if time.monotonic() - start > 60 else failures + 1
            await self.pause((wss_auth_delay(auth_failures) if auth_failures else min(60,2**min(failures,6)))+random.random())

    async def pause(self, seconds):
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)

    async def ticks(self):
        while not self.stop.is_set():
            rows = self.store.projects(include_removed=True)
            signature=tuple(sorted((r['subscription_id'],r['handle'],r['generation'],r['desired']) for r in rows))
            if self._subscription_signature is not None and signature!=self._subscription_signature:
                self._watch_requested=True;self._watch_retry_at=0;self.ledger.request_watch_check(force=True)
            self._subscription_signature=signature
            if self.ledger.watch_pending():self._watch_requested=True
            if self._watch_requested and time.time()>=self._watch_retry_at:
                await self.reconcile()
            await self.process_backfills()
            self.ledger.publish()
            await self.pause(self.cfg.reconcile_seconds)

    async def pulse(self):
        while not self.stop.is_set():
            self.ensure_owner()
            await self.pause(2)

    async def retention(self):
        from .retention import backup_database, cleanup

        while not self.stop.is_set():
            self.ensure_owner()
            self.store.check_retention_clock()
            result = await asyncio.to_thread(
                cleanup,
                self.store,
                owner=self.worker_id,
                backup=lambda path, **kw: backup_database(path, cancel=self.stop.is_set, **kw),
            )
            delay = 300
            if result["state"] in ("blocked_backup", "clock_anomaly"):
                logging.getLogger(__name__).warning("tracking_retention_%s", result["state"])
            if result["state"] == "blocked_backup":
                with self.store.connect() as db:
                    retry = db.execute(
                        "SELECT retry_at_ms FROM retention_jobs ORDER BY created_at_ms DESC LIMIT 1"
                    ).fetchone()
                    if retry:
                        delay = min(300, max(1, retry[0] / 1000 - time.time()))
            await self.pause(delay)

    async def translations(self):
        # Owner decision 2026-10-18: push first, translate afterwards; failures never affect the feed.
        from .translate import run_pass

        failures: dict = {}
        while not self.stop.is_set():
            try:
                stored = await asyncio.to_thread(run_pass, self.store, failures)
            except Exception:  # noqa: BLE001 - translation must never stop the worker
                logging.getLogger(__name__).warning("tracking_translate_pass_failed")
                stored = 0
            await self.pause(1 if stored else 3)

    def retry_adoptions(self):
        for row in self.store.projects():
            if self.adoptable(row) and row['desired']=='running' and row['error']=='ownership_conflict':
                # Recheck authorization with a fresh snapshot; keep the error until verified.
                self.store.observe(row,next_retry=0)

    async def run(self):
        self.acquire()
        self.retry_adoptions()
        tasks = [
            asyncio.create_task(self.translations()),
            asyncio.create_task(self.ticks()),
            asyncio.create_task(self.streams()),
            asyncio.create_task(self.pulse()),
            asyncio.create_task(self.retention()),
            asyncio.create_task(self.stop.wait()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            self.stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.ledger.mark_gap(self.store.runtime().get('pong_at') or time.time())
            await self.remote.close()
            self.release()
