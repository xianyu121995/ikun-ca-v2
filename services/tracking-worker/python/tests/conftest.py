import httpx
import pytest

from tracking.config import Config
from tracking.remote import OTHER_FLAGS, Remote
from tracking.store import Store
from tracking.worker import Worker


class Vendor:
    def __init__(self):
        self.rows, self.tweets, self.calls = {}, [], []
        self.quota = False
        self.add_noop = False
        self.delete_noop = False
        self.uncertain_add = False
        self.list_fails = False

    def watch(self, username, group="ikun-ca-v2-project-tracking"):
        return {
            "twAccount": username,
            "groupName": group,
            "newTweetBol": True,
            **{k: False for k in OTHER_FLAGS},
        }

    def __call__(self, req):
        import json

        endpoint = req.url.path.rsplit("/", 1)[-1]
        body = json.loads(req.content)
        self.calls.append((endpoint, body))
        if endpoint == "twitter_watch":
            if self.list_fails:
                return httpx.Response(503)
            return httpx.Response(200, json={"success": True, "data": list(self.rows.values())})
        if endpoint == "twitter_watch_add":
            if self.quota:
                return httpx.Response(200, json={"success": False, "message": "监控名额达到上限"})
            if not self.add_noop:
                self.rows[body["username"]] = self.watch(body["username"], body["groupName"])
            if self.uncertain_add:
                raise httpx.ReadTimeout("sensitive URL must never escape", request=req)
            return httpx.Response(200, json={"success": True})
        if endpoint == "twitter_watch_delete":
            if not self.delete_noop:
                self.rows.pop(body["username"], None)
            return httpx.Response(200, json={"success": True})
        if endpoint == "twitter_user_tweets":
            return httpx.Response(200, json={"success": True, "data": self.tweets})
        raise AssertionError(endpoint)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("IKUN_TRACKING_6551_TOKEN", "test-vendor-credential-xxxxxxxxxxxxxxxx")
    monkeypatch.setenv("IKUN_TRACKING_ADMIN_TOKEN", "test-admin-credential-xxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("IKUN_TRACKING_READ_TOKEN", "test-reader-credential-xxxxxxxxxxxxxxxx")
    return Config(
        db_path=tmp_path / "tracking.db",
        remote_enabled=True,
        dedicated_account=True,
        request_interval=0,
        reconcile_seconds=0.1,
        heartbeat_seconds=0.1,
        heartbeat_timeout=0.2,
        backfill_seconds=0.1,
    )


@pytest.fixture
def store(cfg):
    return Store(cfg.db_path)


@pytest.fixture
def vendor():
    return Vendor()


@pytest.fixture
async def worker(cfg, store, vendor):
    remote = Remote(cfg, transport=httpx.MockTransport(vendor))
    worker = Worker(cfg, store, remote)
    yield worker
    await remote.close()


def add(store, project="prj_550e8400-e29b-41d4-a716-446655440001", username="project1"):
    return store.mutate(
        "create",
        project,
        {"name": "项目一", "handle": username, "confirmed": True},
        "owner",
        "create-" + project,
    )


def tweet(username="project1", tweet_id="12345", at=None, **extra):
    import time

    return {
        "id": tweet_id,
        "text": "真实协议测试推文",
        "createdAt": at or time.time(),
        "userScreenName": username,
        **extra,
    }


def event(content=None, username="project1", kind="NEW_TWEET"):
    return {
        "jsonrpc": "2.0",
        "method": "twitter.event",
        "params": {"twAccount": username, "eventType": kind, "content": content or tweet(username)},
    }
