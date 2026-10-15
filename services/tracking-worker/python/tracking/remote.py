from __future__ import annotations

import asyncio
import time

import httpx

from .config import Config
from .store import handle

OTHER_FLAGS = (
    "newFlwBol",
    "newUnFlwBol",
    "newTweetReplyBol",
    "newTweetQuoteBol",
    "newRetweetBol",
    "updateNameBol",
    "updateDescBol",
    "updateAvatarBol",
    "updateBannerBol",
    "newCaBol",
    "tweetToppingBol",
)


class RemoteError(Exception):
    def __init__(self, code="api_failure", retry_after=0):
        # Never include raw remote text, request URLs, credentials or response bodies in exceptions.
        super().__init__(code)
        self.code, self.retry_after = code, retry_after


class Remote:
    def __init__(self, cfg: Config, transport=None):
        self.cfg = cfg
        self.client = httpx.AsyncClient(
            base_url="https://ai.6551.io",
            timeout=15,
            follow_redirects=False,
            transport=transport,
            headers={"Authorization": f"Bearer {cfg.secret('token')}"},
        )
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    def ready(self):
        if not self.cfg.remote_enabled or not self.cfg.dedicated_account or not self.cfg.secret("token"):
            raise RemoteError("remote_not_configured")

    async def close(self):
        await self.client.aclose()

    async def request(self, endpoint: str, body: dict):
        self.ready()
        async with self.lock:
            await asyncio.sleep(max(0, self.cfg.request_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = await self.client.post("/open/" + endpoint, json=body)
                if response.status_code == 429:
                    try:
                        delay = min(3600, max(1, float(response.headers.get("Retry-After", 60))))
                    except ValueError:
                        delay = 60
                    raise RemoteError("rate_limited", delay)
                if response.status_code in (401, 403):
                    raise RemoteError("remote_auth_failed", 300)
                if response.status_code >= 400:
                    raise RemoteError("api_failure")
                data = response.json()
                if not isinstance(data, dict):
                    raise RemoteError("invalid_response")
                if data.get("success") is not True:
                    message = str(data.get("message", data.get("msg", data.get("error", "")))).lower()
                    code = (
                        "quota_exhausted"
                        if any(x in message for x in ("quota", "limit", "capacity", "名额", "上限", "额度"))
                        else "api_failure"
                    )
                    raise RemoteError(code, 60 if code == "quota_exhausted" else 0)
                return data.get("data")
            except (httpx.HTTPError, ValueError):
                raise RemoteError("request_uncertain") from None

    async def watches(self) -> dict[str, dict]:
        data = await self.request("twitter_watch", {})
        if isinstance(data, dict):
            rows = data.get("list", data.get("items"))
            if not isinstance(rows, list) or data.get("total", len(rows)) != len(rows):
                raise RemoteError("incomplete_watch_snapshot")
        else:
            rows = data
        if not isinstance(rows, list):
            raise RemoteError("invalid_watch_snapshot")
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                raise RemoteError("invalid_watch_snapshot")
            try:
                account = handle(row.get("twAccount", row.get("username", "")))
            except (ValueError, AttributeError):
                raise RemoteError("invalid_watch_snapshot") from None
            if account in result:
                raise RemoteError("duplicate_watch_identity")
            result[account] = row
        return result

    async def add(self, username):
        return await self.request(
            "twitter_watch_add",
            {
                "username": username,
                "groupName": self.cfg.watch_group,
                "newTweetBol": True,
                **{flag: False for flag in OTHER_FLAGS},
            },
        )

    async def delete(self, username):
        return await self.request("twitter_watch_delete", {"username": username})

    async def tweets(self, username):
        data = await self.request(
            "twitter_user_tweets",
            {
                "username": username,
                "maxResults": 100,
                "product": "Latest",
                "includeReplies": False,
                "includeRetweets": False,
            },
        )
        rows = data.get("list", data.get("tweets")) if isinstance(data, dict) else data
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise RemoteError("invalid_tweet_snapshot")
        return rows
