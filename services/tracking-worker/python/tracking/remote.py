from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from provider_6551 import Ledger, configured

from .config import Config
from .store import handle
from .xstream import (
    OTHER_FLAGS,
    RULES_PATH,
    STREAM_PATH,
    STREAM_QUERY,
    TAG_PREFIX,
    RuleError,
    standard_value,
    watch_from_rule,
)

__all__ = ["OTHER_FLAGS", "Remote", "RemoteError"]


class RemoteError(Exception):
    def __init__(self, code="api_failure", retry_after=0):
        # Never include raw remote text, request URLs, credentials or response bodies in exceptions.
        super().__init__(code)
        self.code, self.retry_after = code, retry_after


def _error_text(data: dict) -> str:
    chunks = []
    errors = data.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            chunks.append(str(item.get("title", "")))
            details = item.get("details")
            if isinstance(details, list):
                chunks.extend(str(detail) for detail in details)
    chunks.append(str(data.get("message", data.get("title", ""))))
    return " ".join(chunks).lower()


def _quota_text(text: str) -> bool:
    return any(word in text for word in ("quota", "rule limit", "rulescap", "capacity", "名额", "上限", "额度"))


def _summary(data: dict) -> dict:
    meta = data.get("meta")
    summary = meta.get("summary") if isinstance(meta, dict) else None
    return summary if isinstance(summary, dict) else {}


class Remote:
    """Filtered-stream rules for the accounts tracking already reconciles.

    Add and delete use the rules endpoint and do not open or close the stream.
    Historical timeline reads stay closed: pay-per-use filtered stream has no recovery backfill.
    """

    def __init__(self, cfg: Config, transport=None, *, cache_watch=True):
        self.cfg = cfg
        self.ledger = configured() or Ledger(cfg.db_path.parent.parent / "ops/6551-ledger.sqlite3")
        self.cache_watch = cache_watch
        self._snapshot = None
        self._ids: dict[str, str] = {}
        self.client = httpx.AsyncClient(
            base_url="https://api.x.com",
            timeout=15,
            follow_redirects=False,
            transport=transport,
            headers={
                "Authorization": f"Bearer {cfg.secret('token')}",
                "User-Agent": "ikun-tracking",
            },
        )
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    def ready(self):
        if not self.cfg.remote_enabled or not (self.cfg.dedicated_account or self.cfg.shared_account_safe) or not self.cfg.secret("token"):
            raise RemoteError("remote_not_configured")

    async def close(self):
        await self.client.aclose()

    def rules_stale(self) -> bool:
        with self.ledger.db() as db:
            requested = self.ledger.get(db, "watch_requested_at", 0) or 0
            done = self.ledger.get(db, "x_rules_epoch", 0) or 0
        return requested != done

    def _ack_rules(self):
        with self.ledger.db() as db:
            db.execute("BEGIN IMMEDIATE")
            requested = self.ledger.get(db, "watch_requested_at", 0) or 0
            self.ledger.put(db, "x_rules_epoch", requested)
            db.commit()

    async def request(self, endpoint: str, body: dict | None = None, *, purpose="read", job_key=None):
        # Timeline and search routes are not a live stream. They never reach the network.
        raise RemoteError("backfill_disabled")

    def _raise_for_status(self, response: httpx.Response):
        if response.status_code == 429:
            try:
                delay = min(3600, max(1, float(response.headers.get("Retry-After", 60))))
            except ValueError:
                delay = 60
            raise RemoteError("rate_limited", delay)
        if response.status_code in (401, 403):
            error = RemoteError("remote_auth_failed", 300)
            error.response = response
            raise error
        if response.status_code == 402:
            error = RemoteError("provider_payment_required", 3600)
            error.response = response
            raise error
        if response.status_code >= 400:
            error = RemoteError("api_failure")
            error.response = response
            raise error

    def _parse_json(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError:
            raise RemoteError("request_uncertain") from None
        if not isinstance(data, dict):
            raise RemoteError("invalid_response")
        return data

    def _raise_for_rules_body(self, data: dict):
        text = _error_text(data)
        summary = _summary(data)
        problem = bool(data.get("errors")) or data.get("success") is False or bool(summary.get("invalid") or summary.get("not_created"))
        if not problem:
            return
        quota = _quota_text(text)
        raise RemoteError("quota_exhausted" if quota else "api_failure", 60 if quota else 0)

    async def _send(self, method: str, path: str, body: dict | None = None) -> dict:
        self.ready()
        async with self.lock:
            await asyncio.sleep(max(0, self.cfg.request_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = await self.client.request(method, path, json=body)
            except httpx.HTTPError:
                raise RemoteError("request_uncertain") from None
        self._raise_for_status(response)
        data = self._parse_json(response)
        self._raise_for_rules_body(data)
        return data

    def _snapshot_from(self, rules) -> dict[str, dict]:
        if not isinstance(rules, list):
            raise RemoteError("invalid_watch_snapshot")
        result = {}
        for rule in rules:
            if not isinstance(rule, dict):
                raise RemoteError("invalid_watch_snapshot")
            try:
                watch = watch_from_rule(rule, self.cfg.watch_group)
            except RuleError as exc:
                raise RemoteError(exc.code) from None
            if watch is None:
                continue
            account = watch["twAccount"]
            if account in result:
                raise RemoteError("duplicate_watch_identity")
            result[account] = watch
        return result

    async def watches(self) -> dict[str, dict]:
        if self.cache_watch and self._snapshot is not None and not self.rules_stale():
            return self._snapshot
        data = await self._send("GET", RULES_PATH)
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        if "data" in data and not isinstance(data["data"], list):
            raise RemoteError("invalid_watch_snapshot")
        if "data" not in data and "meta" not in data:
            raise RemoteError("invalid_watch_snapshot")
        rules = data.get("data", [])
        if not isinstance(rules, list):
            raise RemoteError("invalid_watch_snapshot")
        if "result_count" in meta and meta["result_count"] != len(rules):
            raise RemoteError("incomplete_watch_snapshot")
        snapshot = self._snapshot_from(rules)
        self._ids = {account: row["id"] for account, row in snapshot.items()}
        self._snapshot = snapshot
        self._ack_rules()
        return snapshot

    async def add(self, username):
        account = handle(username)
        value = standard_value(account)
        if len(value) > 1024:
            raise RemoteError("api_failure")
        self._snapshot = None
        return await self._send(
            "POST",
            RULES_PATH,
            {"add": [{"value": value, "tag": f"{TAG_PREFIX}{account}"}]},
        )

    async def delete(self, username):
        account = handle(username)
        rule_id = self._ids.get(account)
        if not rule_id:
            self._snapshot = None
            await self.watches()
            rule_id = self._ids.get(account)
        self._snapshot = None
        if not rule_id:
            return None
        return await self._send("POST", RULES_PATH, {"delete": {"ids": [str(rule_id)]}})

    async def tweets(self, username, *, job=None):
        raise RemoteError("backfill_disabled")

    @asynccontextmanager
    async def open_stream(self):
        """One long-lived GET. Rule changes do not use this connection."""
        self.ready()
        timeout = httpx.Timeout(15.0, read=None)
        async with self.client.stream("GET", STREAM_PATH, params=STREAM_QUERY, timeout=timeout) as response:
            if response.status_code != 200:
                await response.aread()
                self._raise_for_status(response)
                raise RemoteError("stream_error")
            if "backfill_minutes" in str(response.request.url):
                raise RemoteError("api_failure")
            yield response.aiter_lines()
