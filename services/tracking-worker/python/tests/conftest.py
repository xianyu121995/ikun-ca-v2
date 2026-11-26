import httpx
import pytest

from tracking.config import Config
from tracking.remote import OTHER_FLAGS, Remote
from tracking.store import Store
from tracking.worker import Worker
from tracking.xstream import OWNED_GROUP, REMARK, rule_for_watch


class Vendor:
    def __init__(self):
        self.rows, self.tweets, self.calls = {}, [], []
        self.quota = False
        self.add_noop = False
        self.delete_noop = False
        self.uncertain_add = False
        self.list_fails = False
        self._next_id = 1000
        self._synthetic = {}

    def watch(self, username, group="ikun-ca-v2-project-tracking"):
        return {
            "twAccount": username,
            "groupName": group,
            "newTweetBol": True,
            **{k: False for k in OTHER_FLAGS},
        }

    def __call__(self, req):
        import json

        path = req.url.path.split("?", 1)[0].rstrip("/")
        if path.endswith("/2/tweets/search/stream/rules") and req.method == "GET":
            self.calls.append(("rules", None))
            if self.list_fails:
                return httpx.Response(503)
            rules = []
            for row in self.rows.values():
                rule = rule_for_watch(row, OWNED_GROUP)
                if "id" not in rule:
                    account = row["twAccount"]
                    if account not in self._synthetic:
                        self._synthetic[account] = str(self._next_id)
                        self._next_id += 1
                    rule = {**rule, "id": self._synthetic[account]}
                rules.append(rule)
            return httpx.Response(200, json={"data": rules, "meta": {"result_count": len(rules)}})
        if path.endswith("/2/tweets/search/stream/rules") and req.method == "POST":
            body = json.loads(req.content)
            if "add" in body:
                self.calls.append(("rules_add", body))
                if self.quota:
                    return httpx.Response(
                        200,
                        json={
                            "meta": {"summary": {"created": 0, "not_created": 1, "valid": 0, "invalid": 1}},
                            "errors": [{"title": "RulesCap", "details": ["rule limit"]}],
                        },
                    )
                value = body["add"][0]["value"]
                account = value.split()[0].split(":", 1)[1]
                if not self.add_noop:
                    row = self.watch(account)
                    row["id"] = str(self._next_id)
                    row["remark"] = REMARK
                    row["newTweetQuoteBol"] = True
                    self._next_id += 1
                    self.rows[account] = row
                if self.uncertain_add:
                    raise httpx.ReadTimeout("sensitive URL must never escape", request=req)
                stored = self.rows.get(account)
                rule = rule_for_watch(stored, OWNED_GROUP) if stored else {"id": "0", **body["add"][0]}
                return httpx.Response(
                    200,
                    json={
                        "data": [rule],
                        "meta": {"summary": {"created": 1, "not_created": 0, "valid": 1, "invalid": 0}},
                    },
                )
            if "delete" in body:
                self.calls.append(("rules_delete", body))
                if not self.delete_noop:
                    ids = {str(item) for item in body["delete"]["ids"]}
                    for key, row in list(self.rows.items()):
                        if str(row.get("id")) in ids or self._synthetic.get(key) in ids:
                            self.rows.pop(key, None)
                            self._synthetic.pop(key, None)
                return httpx.Response(200, json={"meta": {"summary": {"deleted": len(body["delete"]["ids"])}}})
        raise AssertionError(path)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    # Recovery-path regressions opt in explicitly; production defaults to WSS only.
    monkeypatch.setenv('IKUN_TRACKING_BACKFILL_ENABLED','1')
    monkeypatch.setenv('IKUN_6551_BACKFILL_DAILY_LIMIT','300')
    monkeypatch.setenv("TRACKING_API_TOKEN", "b3-tracking-direction-credential-xxxxxxxx")
    monkeypatch.setenv("IKUN_TRACKING_X_BEARER_TOKEN", "test-vendor-credential-xxxxxxxxxxxxxxxx")
    monkeypatch.setenv("IKUN_TRACKING_ADMIN_TOKEN", "test-admin-credential-xxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("IKUN_TRACKING_READ_TOKEN", "test-reader-credential-xxxxxxxxxxxxxxxx")
    return Config(
        db_path=tmp_path / "tracking" / "tracking.db",
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
    return Store(cfg.db_path, initialize=True)


@pytest.fixture
def vendor():
    return Vendor()


@pytest.fixture
async def worker(cfg, store, vendor):
    remote = Remote(cfg, transport=httpx.MockTransport(vendor),cache_watch=False)
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
        "isReply": False,
        "isQuote": False,
        **extra,
    }


def event(content=None, username="project1", kind="NEW_TWEET"):
    return {
        "jsonrpc": "2.0",
        "method": "twitter.event",
        "params": {"twAccount": username, "eventType": kind, "content": content or tweet(username)},
    }
