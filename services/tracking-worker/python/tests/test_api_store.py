import concurrent.futures
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tracking.api import create_app
from tracking.commands import accept, query
from tracking.protocol import Command

PID = "prj_550e8400-e29b-41d4-a716-446655440001"
TOKEN = "b3-tracking-direction-credential-xxxxxxxx"
HEAD = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}


def envelope(**changes):
    body = {
        "schema_version": 1,
        "command_id": "cmd_" + str(uuid.uuid4()),
        "tenant_id": "ikun-main",
        "actor": {"user_id": "fixture-admin", "tenant_id": "ikun-main", "role": "superadmin"},
        "operation": "tracking.create",
        "project_id": PID,
        "subscription_id": None,
        "expected_revision": None,
        "payload": {
            "name": "本地项目",
            "x_user_id": None,
            "x_handle": "project1",
            "notes": "",
            "confirmed": True,
        },
        "issued_at": "2026-10-15T00:00:00.000Z",
    }
    return body | changes


@pytest.fixture
def client(cfg, store, monkeypatch):
    monkeypatch.setenv("TRACKING_API_TOKEN", TOKEN)
    with TestClient(create_app(cfg, store)) as c:
        yield c


def submit(client, body):
    return client.post("/internal/v1/commands", json=body, headers=HEAD)


def test_no_human_login_or_browser_identity(client, store):
    assert (
        client.get(
            "/internal/v1/subscriptions", headers={"Cookie": "tracking_session=fake", "X-Role": "superadmin"}
        ).status_code
        == 401
    )
    assert client.post("/api/tracking/session", json={"token": TOKEN}).status_code == 404
    assert client.get("/api/v1/tracking/subscriptions", headers=HEAD).status_code == 404
    with store.connect() as db:
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('sessions','login_limits')"
        ).fetchall()


def test_b2_exact_wire_ack_result_idempotency_and_lost_ack(client, store):
    body = envelope()
    response = submit(client, body)
    assert response.status_code == 202
    value = response.json()["data"]
    assert set(value) == {
        "command_id",
        "state",
        "project_id",
        "subscription_id",
        "revision",
        "updated_at",
        "error_code",
        "request_id",
    }
    assert value["state"] == "accepted" and value["subscription_id"].startswith("sub_")
    assert value["project_id"] == PID
    assert query(store, body["command_id"], "query-001")["subscription_id"] == value["subscription_id"]
    assert submit(client, body).json()["data"]["subscription_id"] == value["subscription_id"]
    assert submit(client, body | {"payload": body["payload"] | {"name": "different"}}).status_code == 409
    fetched = client.get("/internal/v1/commands/" + body["command_id"], headers=HEAD)
    assert fetched.status_code == 200 and fetched.headers["cache-control"] == "no-store"
    assert (
        client.get("/internal/v1/commands/cmd_" + str(uuid.uuid4()), headers=HEAD).json()["error"]["code"]
        == "NOT_FOUND"
    )
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "foreign"},
        {"actor": {"user_id": "admin", "tenant_id": "foreign", "role": "superadmin"}},
        {"actor": {"user_id": "reader", "tenant_id": "ikun-main", "role": "user"}},
        {"operation": "tracking.exploit"},
        {"schema_version": True},
        {"project_id": "demo-id"},
        {"actor": {"user_id": "fake", "tenant_id": "ikun-main", "role": "admin"}},
    ],
)
def test_wire_scope_and_actor_rejection(client, change):
    assert submit(client, envelope(**change)).status_code in (403, 422)


def test_foreign_service_or_provider_credential_rejected(client):
    for token in ("hunter-direction", "provider-credential"):
        assert (
            client.get("/internal/v1/subscriptions", headers={"Authorization": "Bearer " + token}).status_code
            == 401
        )
    assert client.get("/internal/v1/subscriptions?tenant_id=foreign", headers=HEAD).status_code == 403


def test_subscription_status_requires_fresh_heartbeat_pong_and_remote(client, store):
    sid = submit(client, envelope()).json()["data"]["subscription_id"]
    store.observe(store.get(PID), remote_state="active", observed_at=time.time(), status="running")
    path = "/internal/v1/subscriptions/" + sid
    assert client.get(path, headers=HEAD).json()["data"]["connection"] == "disconnected"
    store.runtime(heartbeat=time.time(), connection="connected", pong_at=time.time())
    current = client.get(path, headers=HEAD).json()["data"]
    assert current["connection"] == "connected" and current["observed_state"] == "running"
    store.observe(store.get(PID), observed_at=time.time() - 100)
    assert client.get(path, headers=HEAD).json()["data"]["observed_state"] == "unknown"
    store.runtime(pong_at=time.time() - 100)
    assert client.get(path, headers=HEAD).json()["data"]["connection"] == "disconnected"
    store.runtime(pong_at=time.time(), heartbeat=time.time() - 100)
    assert client.get(path, headers=HEAD).json()["data"]["connection"] == "disconnected"


async def test_remote_result_commands_and_same_subscription_generation(client, worker, store, vendor):
    body = envelope()
    receipt = submit(client, body).json()["data"]
    sid = receipt["subscription_id"]
    assert client.get("/internal/v1/subscriptions/" + PID, headers=HEAD).status_code == 422
    await worker.reconcile()
    assert query(store, body["command_id"], "query-001")["state"] == "succeeded"
    row = store.get(PID)
    assert row["baseline_ready"] == 1
    stop = envelope(
        command_id="cmd_" + str(uuid.uuid4()),
        operation="tracking.stop",
        subscription_id=sid,
        expected_revision=row["revision"],
        payload={},
    )
    assert submit(client, stop).status_code == 202
    assert query(store, stop["command_id"], "query-001")["state"] == "accepted"
    await worker.reconcile()
    assert query(store, stop["command_id"], "query-001")["state"] == "succeeded"
    row = store.get(PID)
    resume = envelope(
        operation="tracking.resume", subscription_id=sid, expected_revision=row["revision"], payload={}
    )
    assert submit(client, resume).json()["data"]["subscription_id"] == sid
    assert store.get(PID)["generation"] == 2 and store.get(PID)["baseline_ready"] == 0
    await worker.reconcile()
    assert store.get(PID)["baseline_ready"] == 1
    assert (
        submit(
            client, envelope(operation="tracking.stop", subscription_id=sid, expected_revision=1, payload={})
        ).status_code
        == 409
    )


def test_duplicate_concurrent_inbox_is_one_intent(store):
    cmd = Command.model_validate(envelope())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda i: accept(store, cmd, "concurrent-" + str(i)), range(16)))
    assert len({v["subscription_id"] for v in values}) == 1
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1


def test_platform_id_enrichment_preserves_subscription_and_rejects_collision(client, store):
    first = envelope()
    sid = submit(client, first).json()["data"]["subscription_id"]
    enriched = envelope(payload=first["payload"] | {"x_user_id": "12345", "notes": "not an edit"})
    assert submit(client, enriched).json()["data"]["subscription_id"] == sid
    assert store.get(PID)["x_user_id"] == "12345" and store.get(PID)["notes"] == ""
    other_id = "prj_" + str(uuid.uuid4())
    other = envelope(project_id=other_id, payload=first["payload"] | {"x_handle": "otherproject"})
    other_sid = submit(client, other).json()["data"]["subscription_id"]
    assert (
        submit(
            client, envelope(project_id=other_id, payload=other["payload"] | {"x_user_id": "12345"})
        ).status_code
        == 409
    )
    assert store.get(other_id)["subscription_id"] == other_sid and store.get(other_id)["x_user_id"] is None


async def test_unknown_write_then_read_failure_no_false_success(client, worker, store, vendor):
    body = envelope()
    submit(client, body)
    original = worker.remote.add

    async def uncertain(username):
        await original(username)
        vendor.list_fails = True
        from tracking.remote import RemoteError

        raise RemoteError("request_uncertain")

    worker.remote.add = uncertain
    await worker.reconcile()
    assert query(store, body["command_id"], "check-001")["state"] == "unknown"
    before = sum(e == "twitter_watch_add" for e, _ in vendor.calls)
    vendor.list_fails = False
    store.observe(store.get(PID), next_retry=0)
    await worker.reconcile()
    assert query(store, body["command_id"], "check-001")["state"] == "succeeded"
    assert sum(e == "twitter_watch_add" for e, _ in vendor.calls) == before


async def test_stale_stop_cannot_mutate_superseding_resume(client, worker, store, vendor):
    sid = submit(client, envelope()).json()["data"]["subscription_id"]
    await worker.reconcile()
    submit(client, envelope(operation="tracking.stop", subscription_id=sid, expected_revision=1, payload={}))
    old = store.get(PID)
    submit(
        client, envelope(operation="tracking.resume", subscription_id=sid, expected_revision=2, payload={})
    )
    before = len(vendor.calls)
    await worker.reconcile_one(old, dict(vendor.rows))
    assert len(vendor.calls) == before and "project1" in vendor.rows
    await worker.reconcile()
    assert store.get(PID)["desired"] == "running" and store.get(PID)["remote_state"] == "active"


async def test_stop_does_not_delete_externally_changed_event_flags(client, worker, store, vendor):
    sid = submit(client, envelope()).json()["data"]["subscription_id"]
    await worker.reconcile()
    vendor.rows["project1"]["newFlwBol"] = True
    submit(client, envelope(operation="tracking.stop", subscription_id=sid, expected_revision=1, payload={}))
    await worker.reconcile()
    assert store.get(PID)["error"] == "remote_flags_conflict" and "project1" in vendor.rows
    assert not any(endpoint == "twitter_watch_delete" for endpoint, _ in vendor.calls)


def test_bound_cursor_empty_and_cross_filter(client, store):
    submit(client, envelope())
    for i in range(2):
        submit(
            client,
            envelope(
                project_id="prj_" + str(uuid.uuid4()),
                payload={
                    "name": "p",
                    "x_user_id": None,
                    "x_handle": "test" + str(i),
                    "notes": "",
                    "confirmed": True,
                },
            ),
        )
    first = client.get("/internal/v1/subscriptions?limit=1", headers=HEAD).json()["data"]
    cursor = first["next_cursor"]
    assert cursor
    assert client.get("/internal/v1/subscriptions?cursor=", headers=HEAD).status_code == 422
    assert (
        client.get("/internal/v1/subscriptions?cursor=" + cursor + "&q=other", headers=HEAD).status_code
        == 422
    )
    second = client.get("/internal/v1/subscriptions?cursor=" + cursor + "&limit=1", headers=HEAD).json()[
        "data"
    ]
    assert second["items"][0]["subscription_id"] != first["items"][0]["subscription_id"]


def test_patch_revision_idempotency_and_identity_immutable(client, store):
    sid = submit(client, envelope()).json()["data"]["subscription_id"]
    body = {
        "actor": {"user_id": "fixture-admin", "tenant_id": "ikun-main", "role": "superadmin"},
        "expected_revision": 1,
        "patch": {"name": "edited", "notes": "notes"},
    }
    headers = HEAD | {"Idempotency-Key": str(uuid.uuid4())}
    response = client.patch("/internal/v1/subscriptions/" + sid, json=body, headers=headers)
    assert response.status_code == 200 and response.headers["etag"] == '"rev-2"'
    assert client.patch("/internal/v1/subscriptions/" + sid, json=body, headers=headers).status_code == 200
    assert (
        client.patch(
            "/internal/v1/subscriptions/" + sid,
            json=body | {"patch": {"x_handle": "steal"}},
            headers=HEAD | {"Idempotency-Key": str(uuid.uuid4())},
        ).status_code
        == 422
    )


def test_storage_failure_not_reported_as_missing(client, store, monkeypatch):
    import sqlite3
    from contextlib import contextmanager

    @contextmanager
    def failed():
        raise sqlite3.OperationalError("injected")
        yield

    monkeypatch.setattr(store, "connect", failed)
    response = client.get("/internal/v1/commands/cmd_" + str(uuid.uuid4()), headers=HEAD)
    assert response.status_code == 503 and response.json()["error"]["code"] == "DB_UNAVAILABLE"


async def test_600_capacity_does_not_evict_or_add(client, worker, store, vendor):
    for i in range(600):
        vendor.rows["watch" + str(i)] = vendor.watch("watch" + str(i), "other-independent-owner")
    body = envelope()
    submit(client, body)
    await worker.reconcile()
    assert store.get(PID)["error"] == "quota_exhausted"
    assert len(vendor.rows) == 600
    assert all(name == "twitter_watch" for name, _ in vendor.calls)


async def test_stop_noop_ack_and_timeout_do_not_report_stopped(client, worker, store, vendor):
    body = envelope()
    sid = submit(client, body).json()["data"]["subscription_id"]
    await worker.reconcile()
    vendor.delete_noop = True
    stop = envelope(operation="tracking.stop", subscription_id=sid, expected_revision=1, payload={})
    submit(client, stop)
    await worker.reconcile()
    dto = client.get("/internal/v1/subscriptions/" + sid, headers=HEAD).json()["data"]
    assert dto["observed_state"] == "unknown" and dto["operation_state"] == "unknown"
    assert vendor.rows.get("project1")
    vendor.delete_noop = False
    store.observe(store.get(PID), next_retry=0)
    await worker.reconcile()
    assert query(store, stop["command_id"], "stop-checked")["state"] == "succeeded"
    assert (
        client.get("/internal/v1/subscriptions/" + sid, headers=HEAD).json()["data"]["observed_state"]
        == "absent"
    )


async def test_crash_after_remote_apply_reconciles_without_second_add(client, worker, store, vendor, cfg):
    import asyncio

    from tracking.worker import Worker

    body = envelope()
    submit(client, body)
    original = worker.remote.add

    async def crash(username):
        await original(username)
        raise asyncio.CancelledError()

    worker.remote.add = crash
    with pytest.raises(asyncio.CancelledError):
        await worker.reconcile()
    store.lease("restart", acquire=True)
    assert query(store, body["command_id"], "crash-unknown")["state"] == "unknown"
    replacement = Worker(cfg, store, worker.remote)
    await replacement.reconcile()
    assert query(store, body["command_id"], "crash-checked")["state"] == "succeeded"
    assert sum(name == "twitter_watch_add" for name, _ in vendor.calls) == 1


def test_retention_and_new_path_backup_preserve_pending_inbox(client, store, tmp_path):

    from tracking.store import Store

    body = envelope()
    receipt = submit(client, body).json()["data"]
    with store.connect() as db:
        db.execute("UPDATE commands SET created_at=?", (time.time() - 8 * 86400,))
    target = tmp_path / "restored/tracking/tracking.db"
    from tracking.retention import backup_database, restore

    directory, _ = backup_database(store.path)
    restore(directory, target, store.path, expected_watermark=0)
    restored = Store(target)
    assert query(restored, body["command_id"], "restored")["subscription_id"] == receipt["subscription_id"]
    assert query(restored, body["command_id"], "restored")["state"] == "accepted"


async def test_legacy_generation_ids_and_order_preserved_with_structured_input(client, worker, store):
    from conftest import event, tweet

    from tracking.events import normalize
    from tracking.views import page

    body = envelope()
    sid = submit(client, body).json()["data"]["subscription_id"]
    await worker.reconcile()
    base = store.get(PID)["generation_at"]
    t = tweet(tweet_id="101", text="", at=base + (time.time() - base) * 0.8)
    assert worker.ingest(event(t))
    row = store.get(PID)
    assert store.insert_tweet(
        row, normalize({**t, "text": "completed"}, row["handle"], require_author=True), "rest_recovery"
    )
    assert len(store.activities()) == 1
    # Published and received order are intentionally opposite. Frozen latest remains received descending.
    newer = tweet(tweet_id="102", at=base + (t["createdAt"] - base) * 0.25)
    worker.ingest(event(newer))
    worker.ingest(
        event(
            {
                "id": "103",
                "text": "unknown time",
                "userScreenName": "project1",
                "isReply": False,
                "isQuote": False,
            }
        )
    )
    first = page(store, "latest", {"limit": "1"})
    assert first["items"][0]["tweet_id"] == "103" and first["items"][0]["occurred_at"] is None
    second = page(store, "latest", {"limit": "1", "cursor": first["next_cursor"]})
    assert second["items"][0]["tweet_id"] == "102"
    assert page(store, "activities", {})["items"][0]["text"] == "completed"
    assert worker.ingest(
        event(
            {
                "id": "104",
                "text": "cross-generation",
                "userScreenName": "project1",
                "isReply": False,
                "isQuote": False,
            }
        )
    )
    row = store.get(PID)
    submit(
        client,
        envelope(
            operation="tracking.stop", subscription_id=sid, expected_revision=row["revision"], payload={}
        ),
    )
    await worker.reconcile()
    row = store.get(PID)
    submit(
        client,
        envelope(
            operation="tracking.resume", subscription_id=sid, expected_revision=row["revision"], payload={}
        ),
    )
    await worker.reconcile()
    assert worker.ingest(
        event(
            {
                "id": "104",
                "text": "cross-generation",
                "userScreenName": "project1",
                "isReply": False,
                "isQuote": False,
            }
        )
    )
    observations = [r for r in store.activities() if r["tweet_id"] == "104"]
    assert len(observations) == 2 and observations[0]["activity_id"] != observations[1]["activity_id"]
    # Legacy generation observations remain distinct; published-v1 folding is tested separately.
    assert len(page(store, "latest", {})["items"]) == 5
