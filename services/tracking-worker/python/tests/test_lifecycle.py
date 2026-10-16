import asyncio
import json
import time
from dataclasses import replace

import httpx
import pytest
from conftest import add, event, tweet
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from tracking.remote import Remote, RemoteError
from tracking.store import Conflict, Store
from tracking.worker import Worker


async def test_crud_remote_verified_lifecycle(worker, store, vendor):
    row = add(store)
    assert row["remote_state"] == "unknown"
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    assert row["remote_state"] == "active" and row["claim"] == "owned"
    row = store.mutate(
        "update",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"], "notes": "已核实"},
        "admin",
        "edit-001",
    )
    assert row["notes"] == "已核实"
    row = store.mutate(
        "stop",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "stop-001",
    )
    assert row["status"] == "pending" and row["remote_state"] == "active"
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    assert row["status"] == "stopped" and row["remote_state"] == "absent"
    row = store.mutate(
        "resume",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "resume-001",
    )
    assert row["generation"] == 2
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    store.mutate(
        "remove",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "remove-001",
    )
    assert len(store.projects()) == 1  # A pending removal remains visible.
    await worker.reconcile()
    assert (
        store.get("prj_550e8400-e29b-41d4-a716-446655440001")["status"] == "removed"
        and store.projects() == []
    )
    assert vendor.rows == {}


async def test_noop_success_never_running(worker, store, vendor):
    add(store)
    vendor.add_noop = True
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    assert row["status"] == "retrying" and row["remote_state"] == "unknown"
    assert row["error"] == "remote_verification_failed"


async def test_timeout_after_applied_add_is_resolved_by_read(worker, store, vendor):
    add(store)
    vendor.uncertain_add = True
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["status"] == "running"
    assert sum(e == "twitter_watch_add" for e, _ in vendor.calls) == 1


async def test_failed_delete_visible_retry_no_false_stop(worker, store, vendor):
    add(store)
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    vendor.delete_noop = True
    store.mutate(
        "remove",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "remove-001",
    )
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["status"] == "retrying"
    assert len(store.projects()) == 1
    vendor.delete_noop = False
    store.observe(store.get("prj_550e8400-e29b-41d4-a716-446655440001"), next_retry=0)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["status"] == "removed"


async def test_quota_failure_retry_persisted_and_one_project_does_not_block_others(worker, store, vendor):
    add(store)
    vendor.quota = True
    await worker.reconcile()
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    assert row["error"] == "quota_exhausted" and row["next_retry"] > time.time()
    calls = len(vendor.calls)
    await worker.reconcile()
    assert len(vendor.calls) == calls
    vendor.quota = False
    add(store, "prj_550e8400-e29b-41d4-a716-446655440002", "project2")
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440002")["remote_state"] == "active"
    store.observe(row, next_retry=0)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["remote_state"] == "active"


async def test_shared_watch_never_overwritten_or_deleted(worker, store, vendor):
    add(store)
    vendor.rows["project1"] = vendor.watch("project1", "AlphaPulse")
    vendor.rows["hunter"] = vendor.watch("hunter", "HunterRadar")
    original = json.dumps(vendor.rows, sort_keys=True)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["error"] == "ownership_conflict"
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    store.mutate(
        "remove",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "remove-001",
    )
    await worker.reconcile()
    assert json.dumps(vendor.rows, sort_keys=True) == original
    assert all(e == "twitter_watch" for e, _ in vendor.calls)


async def test_matching_group_without_local_claim_is_not_adopted(worker, store, vendor):
    add(store)
    vendor.rows["project1"] = vendor.watch("project1")
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["error"] == "ownership_conflict"


async def test_external_flag_change_is_blocked(worker, store, vendor):
    add(store)
    await worker.reconcile()
    vendor.rows["project1"]["newFlwBol"] = True
    count = len(vendor.calls)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["error"] == "remote_flags_conflict"
    assert all(e == "twitter_watch" for e, _ in vendor.calls[count:])


async def test_list_failure_blocks_all_mutations_and_recovers(worker, store, vendor):
    add(store)
    vendor.list_fails = True
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["remote_state"] == "unknown"
    assert all(e == "twitter_watch" for e, _ in vendor.calls)
    vendor.list_fails = False
    store.observe(store.get("prj_550e8400-e29b-41d4-a716-446655440001"), next_retry=0)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["remote_state"] == "active"


async def test_revision_race_does_not_overwrite_stop(worker, store, vendor):
    add(store)
    original = worker.remote.add

    async def racing_add(username):
        row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
        store.mutate(
            "stop",
            "prj_550e8400-e29b-41d4-a716-446655440001",
            {"expected_revision": row["revision"]},
            "admin",
            "racing-stop",
        )
        return await original(username)

    worker.remote.add = racing_add
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["desired"] == "stopped"
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["status"] == "pending"
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["remote_state"] == "absent"


async def test_restart_recovers_reserved_remote_add_without_duplicate(worker, store, vendor, cfg):
    row = add(store)
    store.observe(row, claim="reserved")
    vendor.rows["project1"] = vendor.watch("project1")
    replacement = Worker(cfg, Store(cfg.db_path), worker.remote)
    await replacement.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["claim"] == "owned"
    assert all(e != "twitter_watch_add" for e, _ in vendor.calls)


async def test_disabled_remote_makes_zero_requests(cfg, store, vendor):
    add(store)
    for settings in (replace(cfg, remote_enabled=False), replace(cfg, dedicated_account=False)):
        remote = Remote(settings, transport=httpx.MockTransport(vendor))
        worker = Worker(settings, store, remote)
        store.observe(store.get("prj_550e8400-e29b-41d4-a716-446655440001"), next_retry=0)
        await worker.reconcile()
        assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["error"] == "remote_not_configured"
        await remote.close()
    assert not vendor.calls


def test_single_worker_lock_release_on_restart(worker, cfg, store):
    worker.acquire()
    second = Worker(cfg, store, worker.remote)
    with pytest.raises(RuntimeError, match="another tracking worker"):
        second.acquire()
    worker.release()
    second.acquire()
    second.release()


def test_confirmation_duplicates_revision_and_idempotency(store):
    with pytest.raises(ValueError):
        store.mutate("create", "bad", {"confirmed": False}, "admin", "no-confirm")
    row = add(store)
    assert add(store) == row
    with pytest.raises(Conflict):
        add(store, "prj_550e8400-e29b-41d4-a716-446655440002", "project1")
    with pytest.raises(Conflict):
        store.mutate(
            "stop", "prj_550e8400-e29b-41d4-a716-446655440001", {"expected_revision": 99}, "admin", "stop-key"
        )
    with pytest.raises(Conflict):
        store.mutate(
            "create",
            "prj_550e8400-e29b-41d4-a716-446655440002",
            {"confirmed": True},
            "owner",
            "create-prj_550e8400-e29b-41d4-a716-446655440001",
        )


async def test_backfill_dedup_filters_and_gap_reporting(worker, store, vendor):
    add(store)
    old = tweet(at=time.time() - 86400, tweet_id="1")
    now = tweet(tweet_id="2")
    vendor.tweets = [old, now, tweet(tweet_id="3", isReply=True), tweet("foreign", "4")]
    await worker.reconcile()
    assert [x["tweet_id"] for x in store.activities()] == ["2"]
    assert not worker.ingest(event(now))
    vendor.tweets = [tweet(tweet_id=str(1000 + i)) for i in range(100)]
    store.observe(store.get("prj_550e8400-e29b-41d4-a716-446655440001"), last_backfill=0)
    await worker.reconcile()
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["coverage"] == "possible_gap"


@pytest.mark.parametrize("kind", ["NEW_FOLLOWER", "NEW_TWEET_REPLY", "NEW_RETWEET"])
async def test_only_new_tweet(worker, store, kind):
    add(store)
    await worker.reconcile()
    assert not worker.ingest(event(kind=kind))
    assert store.activities() == []


async def test_ingestion_filters_restart_dedup_and_empty_body_completion(worker, store):
    add(store)
    await worker.reconcile()
    t = tweet(text="")
    assert worker.ingest(event(t))
    assert not worker.ingest(event(t))
    assert worker.ingest(event({**t, "text": "正文补全"}))
    assert len(store.activities()) == 1 and store.activities()[0]["text"] == "正文补全"
    assert not worker.ingest(event(tweet("foreign")))
    assert not worker.ingest(event(tweet(at=time.time() - 86400, tweet_id="999")))
    assert worker.ingest(
        event(
            {
                "id": "998",
                "text": "missing timestamp",
                "userScreenName": "project1",
                "isReply": False,
                "isQuote": False,
            }
        )
    )
    assert store.activities()[-1]["created_at"] is None
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    store.mutate(
        "stop",
        "prj_550e8400-e29b-41d4-a716-446655440001",
        {"expected_revision": row["revision"]},
        "admin",
        "stop-001",
    )
    assert not worker.ingest(event(tweet(tweet_id="997")))


async def test_websocket_subscribe_pong_disconnect_and_reconnect(worker, store):
    add(store)
    await worker.reconcile()
    connections = 0

    async def server(ws):
        nonlocal connections
        connections += 1
        number = connections
        async for raw in ws:
            if raw == "ping":
                await ws.send("pong")
                await ws.send(json.dumps(event(tweet(tweet_id=str(900 + number)))))
                if number == 1:
                    await asyncio.sleep(0.05)
                    await ws.close()
            else:
                assert json.loads(raw)["method"] == "twitter.subscribe"
                await ws.send(json.dumps({"id": 1, "result": {"success": True}}))

    async with serve(server, "127.0.0.1", 0) as server:
        url = "ws://127.0.0.1:" + str(server.sockets[0].getsockname()[1])
        worker.ws_connect = lambda ignored, **kwargs: connect(url, **kwargs)
        original_pause = worker.pause
        worker.pause = lambda seconds: original_pause(0.03)
        task = asyncio.create_task(worker.streams())
        try:
            for _ in range(100):
                if len(store.activities()) >= 2 and store.runtime()["connection"] == "connected":
                    break
                await asyncio.sleep(0.03)
            assert connections >= 2
            assert len(store.activities()) == 2
            assert store.runtime()["pong_at"]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_missing_pong_does_not_report_connected(worker, store):
    async def server(ws):
        async for raw in ws:
            if raw != "ping":
                await ws.send(json.dumps({"id": 1, "result": {"success": True}}))

    async with serve(server, "127.0.0.1", 0) as server:
        url = "ws://127.0.0.1:" + str(server.sockets[0].getsockname()[1])
        async with connect(url) as ws:
            with pytest.raises(asyncio.TimeoutError):
                await worker.session(ws)
    assert store.runtime()["connection"] != "connected"


@pytest.mark.parametrize(
    "body,code",
    [
        ({"success": True, "data": {"list": [], "total": 2}}, "incomplete_watch_snapshot"),
        ({"success": True, "data": None}, "invalid_watch_snapshot"),
        ({"success": False, "message": "token-secret"}, "api_failure"),
    ],
)
async def test_remote_fails_closed(cfg, body, code):
    remote = Remote(cfg, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    try:
        with pytest.raises(RemoteError) as err:
            await remote.watches()
        assert str(err.value) == code and "token-secret" not in str(err.value)
    finally:
        await remote.close()


async def test_rate_limit_backoff(cfg):
    remote = Remote(
        cfg, transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "91"}))
    )
    try:
        with pytest.raises(RemoteError) as err:
            await remote.watches()
        assert err.value.code == "rate_limited" and err.value.retry_after == 91
    finally:
        await remote.close()


@pytest.mark.asyncio
async def test_explicit_owned_legacy_watch_adopts_without_remote_write(worker,store,vendor):
    from dataclasses import replace
    add(store)
    vendor.rows['project1']={**vendor.watch('project1',group='legacy-ikun'),'id':777,'remark':'ikun.website:fixture:1'}
    worker.cfg=replace(worker.cfg,adopted_watch_ids={'project1':'777'})
    await worker.reconcile()
    row=store.get('prj_550e8400-e29b-41d4-a716-446655440001')
    assert row['claim']=='owned' and row['remote_state']=='active'
    assert not any(endpoint in ('twitter_watch_add','twitter_watch_delete') for endpoint,body in vendor.calls)
