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

log = logging.getLogger("tracking.worker")


class Worker:
    def __init__(self, cfg: Config, store: Store, remote: Remote, ws_connect=connect):
        self.cfg, self.store, self.remote, self.ws_connect = cfg, store, remote, ws_connect
        self.stop = asyncio.Event()
        self.worker_id = str(uuid.uuid4())
        self._leased = False
        self._last_reconcile = 0

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

    def owned(self, row, watch):
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
        delay = max(exc.retry_after, min(300, 2 ** min(attempts, 8)) + random.random())
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
        if watch and not self.owned(row, watch):
            raise RemoteError("ownership_conflict", 300)
        desired_running = row["desired"] == "running"
        if watch and not self.pure_tweet(watch):
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
            matches = (bool(watch) and self.pure_tweet(watch)) if desired_running else watch is None
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
        )
        if updated and desired_running:
            await self.backfill({**row, "remote_state": state, "claim": claim})
        return snapshot

    async def backfill(self, row):
        if row["last_backfill"] and time.time() - row["last_backfill"] < self.cfg.backfill_seconds:
            return
        boundary = max(row["generation_at"], self.store.latest_time(row["project_id"]) or 0)
        try:
            items = await self.remote.tweets(row["handle"])
            self.ensure_owner()
            tweets = [
                normalize(item, row["handle"], require_author=True, event_type="REST_USER_TWEETS_NO_RETWEETS")
                for item in items
            ]
            valid = [tweet for tweet in tweets if tweet]
            coverage = "bounded_latest_100"
            if len(items) >= 100 and (not valid or min(x["created_at"] for x in valid) > boundary):
                coverage = "possible_gap"
            if row["coverage"] == "possible_gap":
                coverage = "possible_gap"  # Later success cannot prove a previously lost window.
            for tweet in sorted(valid, key=lambda x: x["created_at"]):
                self.store.insert_tweet(row, tweet, "rest_recovery")
            self.store.observe(row, last_backfill=time.time(), coverage=coverage, baseline_ready=1)
        except RemoteError:
            self.store.observe(
                row,
                last_backfill=time.time(),
                coverage="possible_gap" if row["coverage"] == "possible_gap" else "recovery_failed",
            )

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
            snapshot = await self.remote.watches()
            self._last_reconcile = now
        except RemoteError as exc:
            for row in rows:
                self.fail(row, exc)
            return
        for row in rows:
            if self.stop.is_set():
                break
            try:
                snapshot = await self.reconcile_one(row, snapshot)
            except RemoteError as exc:
                self.fail(row, exc)
                # A possibly applied mutation invalidates the prior snapshot.
                try:
                    snapshot = await self.remote.watches()
                except RemoteError as list_exc:
                    for pending in rows[rows.index(row) + 1 :]:
                        self.fail(pending, list_exc)
                    break

    def ingest(self, message):
        self.ensure_owner()
        event = parse_event(message)
        if event is None:
            return False
        username, tweet = event
        row = next((r for r in self.store.projects() if r["handle"] == username), None)
        if not row or row["desired"] != "running" or row["claim"] != "owned":
            return False
        if (
            row["remote_state"] != "active"
            or time.time() - (row["observed_at"] or 0) > self.cfg.remote_fresh_seconds
        ):
            return False
        return self.store.insert_tweet(row, tweet, "wss")

    async def session(self, ws):
        ack, pong = asyncio.Event(), asyncio.Event()

        async def receiver():
            async for raw in ws:
                if raw in ("pong", b"pong"):
                    pong.set()
                    continue
                if raw in ("ping", b"ping"):
                    await ws.send("pong")
                    continue
                try:
                    message = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(message, dict):
                    continue
                params = message.get('params')
                if isinstance(params,dict) and str(params.get('twAccount','')).lower() == '0x2a_ikun':
                    logging.getLogger('tracking.target.raw').info(json.dumps({'received_at':time.time(),'frame':raw.decode() if isinstance(raw,bytes) else raw},ensure_ascii=False))
                if message.get("id") == 1:
                    if message.get("result", {}).get("success") is True:
                        ack.set()
                    else:
                        raise RemoteError("subscription_rejected")
                elif message.get("error"):
                    raise RemoteError("stream_error")
                elif ack.is_set():
                    self.ingest(message)
            raise RemoteError("stream_closed")

        async def heartbeat():
            await asyncio.wait_for(ack.wait(), timeout=self.cfg.heartbeat_timeout)
            while True:
                pong.clear()
                await ws.send("ping")
                await asyncio.wait_for(pong.wait(), timeout=self.cfg.heartbeat_timeout)
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
        while not self.stop.is_set():
            start = time.monotonic()
            try:
                self.remote.ready()
                self.store.runtime(connection="connecting", pong_at=None, error=None)
                url = "wss://ai.6551.io/open/twitter_wss?" + urlencode({"token": self.cfg.secret("token")})
                async with self.ws_connect(
                    url,
                    open_timeout=15,
                    close_timeout=5,
                    ping_interval=None,
                    max_size=1024 * 1024,
                    max_queue=64,
                ) as ws:
                    await self.session(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.stop.is_set():
                    break
                code = exc.code if isinstance(exc, RemoteError) else "stream_disconnected"
                self.store.runtime(connection="disconnected", pong_at=None, error=code)
                # Logging only the classification avoids leaking a token-bearing handshake URL.
                log.warning("stream disconnected: %s", code)
            failures = 0 if time.monotonic() - start > 60 else failures + 1
            await self.pause(min(60, 2 ** min(failures, 6)) + random.random())

    async def pause(self, seconds):
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)

    async def ticks(self):
        while not self.stop.is_set():
            rows = self.store.projects(include_removed=True)
            if time.time()-self._last_reconcile >= min(300,self.cfg.remote_fresh_seconds/2) or any(r['next_retry'] <= time.time() and (r['status'] not in ('running','stopped','removed') or r['error']) for r in rows):
                await self.reconcile()
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

    async def run(self):
        self.acquire()
        tasks = [
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
            await self.remote.close()
            self.release()
