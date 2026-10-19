import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from conftest import add, tweet
from fastapi.testclient import TestClient

from tracking import feed, retention
from tracking.api import create_app
from tracking.events import normalize, parse_event
from tracking.migration import APP_ID, SCHEMAS, hashes, inspect, migrate
from tracking.protocol import DomainError
from tracking.store import Store

ACTOR = {"user_id": "usr_test", "tenant_id": "ikun-main", "role": "user"}
QUERY = {"q": "", "ratings": ["S", "A", "B"], "subscription_id": None, "from_at": None, "until_at": None}


def target(store, index=1):
    row = add(store, "prj_" + str(uuid.uuid4()), "project" + str(index))
    with store.connect() as db:
        db.execute(
            "UPDATE projects SET generation_at=1,notes=? WHERE project_id=?",
            ("真实备注 " + str(index), row["project_id"]),
        )
    return store.get(row["project_id"])


def observe(store, row, identifier, *, at=None, kind="original", text="body", source="wss"):
    content = tweet(
        row["handle"],
        str(identifier),
        at=at or time.time() - 1,
        text=text,
        isQuote=kind == "quote",
        isReply=kind == "reply",
    )
    item = normalize(content, row["handle"])
    item["tweet_kind"] = kind
    return store.insert_tweet(row, item, source)


def request_basis(store, **query):
    return feed.basis(
        store,
        feed.BasisRequest.model_validate(
            {"schema_version": 1, "actor": ACTOR, "profile": "published-v1", "query": QUERY | query}
        ),
    )


def project_ratings(basis, mapping=None):
    mapping = mapping or {}
    rows = []
    for pid in basis["project_ids"]:
        grade = mapping.get(pid, "A")
        rows.append(
            {
                "project_id": pid,
                "state": "missing" if grade == "missing" else "found",
                "rating": None if grade == "missing" else grade,
                "revision": None if grade == "missing" else 1,
            }
        )
    return {
        "contract": "tracking-ratings-v1",
        "catalog_version": "catalog-v1" if rows else None,
        "checked_at": feed.iso(retention.wall_ms()),
        "items": rows,
    }


def make_page(store, limit=2, mapping=None, **query):
    basis = request_basis(store, **query)
    return feed.snapshot(
        store,
        feed.SnapshotRequest.model_validate(
            {
                "schema_version": 1,
                "actor": ACTOR,
                "basis_id": basis["basis_id"],
                "query_hash": basis["query_hash"],
                "limit": limit,
                "ratings_snapshot": project_ratings(basis, mapping),
            }
        ),
    )


def next_page(store, cursor, limit=2, **changes):
    return feed.page(
        store,
        feed.PageRequest.model_validate(
            {
                "schema_version": 1,
                "actor": ACTOR,
                "cursor": cursor,
                "limit": limit,
                "verified_catalog_version": "catalog-v1",
            }
            | changes
        ),
    )


@pytest.mark.parametrize("quote_scope", ["self", "other_tracked", "untracked"])
@pytest.mark.parametrize("event_kind", ["NEW_TWEET", "NEW_TWEET_QUOTE"])
def test_official_quote_adapter_all_quoted_authors(quote_scope, event_kind):
    content = tweet(isQuote=True, quotedStatus={"userScreenName": quote_scope})
    packet = {
        "method": "twitter.event",
        "params": {"twAccount": "project1", "eventType": event_kind, "content": content},
    }
    assert parse_event(packet)[1]["tweet_kind"] == "quote"
    content["isReply"] = True
    assert parse_event(packet)[1]["tweet_kind"] == "reply"


@pytest.mark.parametrize("field,value", [("isReply", "false"), ("isQuote", "true"), ("isRetweet", 1)])
def test_invalid_boolean_evidence_is_unknown(field, value):
    assert normalize(tweet(**{field: value}), "project1")["tweet_kind"] == "unknown"


def test_author_and_unknown_are_not_fabricated(store):
    row = target(store)
    assert normalize({"id": "1", "text": "not authoritative"}, row["handle"]) is None
    assert normalize(tweet("someoneelse"), "project1") is None
    unknown = normalize({"id": "2", "text": "unknown", "userScreenName": row["handle"]}, row["handle"], event_type="UNRECOGNIZED")
    assert unknown["tweet_kind"] == "unknown"
    assert store.insert_tweet(row, unknown, "wss")
    assert make_page(store)["items"] == []
    assert make_page(store)["excluded"]["unknown_type"] == 1
    known = normalize(tweet(row["handle"], "2", text="known"), "project1")
    assert store.insert_tweet(row, known, "wss")
    assert len(make_page(store)["items"]) == 1
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'"
            ).fetchone()[0]
            == 0
        )


def test_stable_fold_dedup_no_new_event_after_generation_restart_or_new_sub(store):
    row = target(store)
    assert observe(store, row, "10")
    first = make_page(store)["items"][0]
    with store.connect() as db:
        db.execute("UPDATE projects SET generation=generation+1 WHERE project_id=?", (row["project_id"],))
    row = store.get(row["project_id"])
    assert observe(store, row, "10", source="rest")
    second = make_page(store)["items"][0]
    assert first["activity_id"] == second["activity_id"] == feed.activity_id(row["subscription_id"], "10")
    assert len(store.activities()) == 2
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'"
            ).fetchone()[0]
            == 1
        )
        db.execute(
            "UPDATE projects SET subscription_id=? WHERE project_id=?",
            ("sub_" + str(uuid.uuid4()), row["project_id"]),
        )
    assert not observe(store, store.get(row["project_id"]), "10")
    assert len(Store(store.path).activities()) == 2


def test_server_global_sort_full_counts_filters_and_limit_change(store):
    rows = [target(store, index) for index in range(1, 8)]
    mapping = dict(
        zip([row["project_id"] for row in rows], ["S", "A", "B", "C", "D", None, "missing"], strict=True)
    )
    for i, row in enumerate(rows):
        observe(store, row, 100 + i, at=time.time() - 100 + i)
    observe(store, rows[0], "201", at=time.time() - 200, kind="reply")
    observe(store, rows[0], "202", at=time.time() - 200, kind="repost")
    observe(store, rows[0], "203", at=time.time() - 200, kind="unknown")
    observe(store, rows[0], "204", at=time.time() - 200, kind="quote")
    result = make_page(store, limit=1, mapping=mapping)
    assert result["matched_total"] == 4
    assert result["activity_counts_by_rating"] == {"S": 2, "A": 1, "B": 1}
    assert result["subscription_counts_by_rating"] == {"S": 1, "A": 1, "B": 1}
    assert result["excluded"] == {
        "reply": 1,
        "repost": 1,
        "unknown_type": 1,
        "C": 1,
        "D": 1,
        "unrated": 1,
        "missing_project": 1,
    }
    seen = result["items"][:]
    while result["next_cursor"]:
        result = next_page(store, result["next_cursor"], limit=2)
        seen += result["items"]
    assert [r["tweet_id"] for r in seen] == ["102", "101", "100", "204"]
    assert len({r["activity_id"] for r in seen}) == 4
    filtered = make_page(store, mapping=mapping, q="真实备注 1", ratings=["S"])
    assert filtered["matched_total"] == 2
    assert filtered["subscription_counts_by_rating"] == {"S": 1, "A": 1, "B": 1}
    assert filtered["items"][0]["notes"] == "真实备注 1"


def test_unknown_time_fallback_cursor_tamper_and_user_binding(store):
    row = target(store)
    t = normalize(
        {
            "id": "30",
            "text": "no timestamp",
            "userScreenName": row["handle"],
            "isReply": False,
            "isQuote": False,
        },
        row["handle"],
    )
    store.insert_tweet(row, t, "wss")
    observe(store, row, "31", at=time.time() - 1)
    result = make_page(store, limit=1)
    assert result["items"][0]["sort_basis"] == "received_at"
    assert result["items"][0]["occurred_at"] is None
    cursor = result["next_cursor"]
    with pytest.raises(DomainError) as other:
        next_page(store, cursor, actor=ACTOR | {"user_id": "usr_other"})
    assert other.value.status == 404
    with pytest.raises(DomainError) as bad:
        next_page(store, cursor + "x")
    assert bad.value.status == 422
    with pytest.raises(DomainError) as changed:
        next_page(store, cursor, verified_catalog_version="catalog-v2")
    assert changed.value.status == 409


def test_new_arrivals_excluded_but_existing_semantic_changes_invalidate_snapshot(store):
    row = target(store)
    for i in range(3):
        observe(store, row, 40 + i)
    first = make_page(store, limit=1)
    observe(store, row, "49")
    assert next_page(store, first["next_cursor"])["matched_total"] == 3
    with store.connect() as db:
        db.execute("UPDATE projects SET notes=? WHERE project_id=?", ("new note", row["project_id"]))
    with pytest.raises(DomainError) as changed:
        next_page(store, first["next_cursor"])
    assert changed.value.status == 409


def test_incomplete_stale_or_false_ratings_never_make_empty_success(store, monkeypatch):
    row = target(store)
    observe(store, row, "50")
    base = request_basis(store)
    projection = project_ratings(base)
    projection["items"] = []
    value = {
        "schema_version": 1,
        "actor": ACTOR,
        "basis_id": base["basis_id"],
        "query_hash": base["query_hash"],
        "limit": 2,
        "ratings_snapshot": projection,
    }
    with pytest.raises(DomainError) as missing:
        feed.snapshot(store, feed.SnapshotRequest.model_validate(value))
    assert missing.value.status == 503
    projection = project_ratings(base)
    projection["checked_at"] = feed.iso(retention.wall_ms() - 16000)
    with pytest.raises(DomainError) as stale:
        feed.snapshot(store, feed.SnapshotRequest.model_validate(value | {"ratings_snapshot": projection}))
    assert stale.value.status == 503


def test_capacity_and_empty_no_ratings_source(store):
    empty = make_page(store)
    assert empty["matched_total"] == 0 and empty["snapshot"]["ratings_source_state"] == "not_needed"
    for _ in range(7):
        request_basis(store)
    with pytest.raises(DomainError) as full:
        request_basis(store)
    assert full.value.status == 429


def test_ttl_boundary_backwards_clock_and_hidden_before_failed_backup(store, monkeypatch):
    row = target(store)
    observe(store, row, "60")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry - 1)
    assert make_page(store)["matched_total"] == 1
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry)
    assert make_page(store)["items"] == []

    def fail(*a, **kw):
        raise OSError("synthetic disk full")

    assert retention.cleanup(store, backup=fail)["state"] == "blocked_backup"
    with store.connect() as db:
        assert db.execute("SELECT text FROM tweets").fetchone()[0] == "body"
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry - 100000)
    assert make_page(store)["items"] == []
    assert not observe(store, row, "60")


def test_verified_cleanup_removes_every_payload_copy_but_preserves_commands_and_ledger(store, monkeypatch):
    row = target(store)
    observe(store, row, "70", text="expired unique body")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]
        db.execute(
            "INSERT INTO tweets_legacy(project_id,handle,tweet_id,text,created_at,received_at,source,generation) VALUES(?,?,?,'expired unique body',1,1,'wss',1)",
            (row["project_id"], row["handle"], "70"),
        )
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry)
    result = retention.cleanup(store)
    assert result["state"] == "completed" and result["deleted"] == 1
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tweets").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM tweets_legacy").fetchone()[0] == 0
        assert (
            db.execute("SELECT COUNT(*) FROM changes WHERE data LIKE '%expired unique body%'").fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM tracking_outbox WHERE envelope LIKE '%expired unique body%'"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT state,original_hash FROM tracking_outbox").fetchone()[0]
            == "expired_pending_reconciliation"
        )
        ledger = dict(db.execute("SELECT * FROM tweet_ledger").fetchone())
        assert (
            ledger["state"] == "expired"
            and ledger["origin_subscription_id"] is None
            and ledger["first_received_at_ms"] is None
        )
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1
    assert not observe(Store(store.path), row, "70")
    manifest = retention.backup_info(Path(result_path(store)))
    assert manifest["ledger_high_water"] >= 1


def result_path(store):
    with store.connect() as db:
        return db.execute("SELECT backup_path FROM retention_jobs ORDER BY created_at_ms DESC").fetchone()[0]


def test_interrupted_purge_rolls_back_and_reuses_verified_backup(store, monkeypatch):
    row = target(store)
    observe(store, row, "80")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry)
    assert retention.cleanup(store, fault="in_delete")["state"] == "blocked_backup"
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tweets").fetchone()[0] == 1
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry + 61000)
    result = retention.cleanup(store)
    assert result["state"] == "completed" and result["deleted"] == 1
    assert len(list((store.path.parent / "backups").glob("*/manifest.json"))) == 1


def test_clock_anomaly_survives_restart_requires_explicit_safe_ack(store):
    now = retention.wall_ms()
    store.check_retention_clock(now_ms=now, monotonic_ms=1000)
    assert store.check_retention_clock(now_ms=now + 400000, monotonic_ms=2000)["clock_anomaly"]
    assert retention.cleanup(Store(store.path))["state"] == "clock_anomaly"
    with pytest.raises(ValueError):
        store.check_retention_clock(now_ms=now - 1, monotonic_ms=3000, acknowledge=True)
    restarted = Store(store.path)
    assert (
        restarted.check_retention_clock(now_ms=now + 400001, monotonic_ms=1, acknowledge=True)[
            "clock_anomaly"
        ]
        is False
    )


def v3(path):
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        for name in ("001_foundation.sql", "002_tracking.sql", "003_commands.sql"):
            db.executescript((SCHEMAS / name).read_text())
        db.execute("INSERT INTO _store_identity VALUES(1,'tracking')")
        db.execute("INSERT INTO runtime(id) VALUES(1)")
        db.execute("CREATE TABLE _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL)")
        for version in (1, 2, 3):
            db.execute(
                "INSERT INTO _schema_migrations VALUES(?,?,?)",
                (version, "foundation" if version == 1 else f"tracking_v{version}", "old"),
            )
            db.execute("INSERT INTO _migration_checksums VALUES(?,?)", (version, hashes()[version]))
        db.execute(f"PRAGMA application_id={APP_ID}")
        db.execute("PRAGMA user_version=3")


def test_v3_upgrade_backup_before_v4_and_failed_upgrade_rollback(tmp_path):
    path = tmp_path / "v3/tracking/tracking.db"
    v3(path)
    with pytest.raises(RuntimeError):
        migrate(path, fault=4)
    inspect(path, maximum=3)
    assert list((path.parent / "backups").glob("*/manifest.json"))
    migrate(path)
    inspect(path)
    with pytest.raises(ValueError):
        inspect(path, maximum=3)


def test_new_path_restore_merges_proven_ledger_and_purges_expired_without_resurrection(
    store, tmp_path, monkeypatch
):
    row = target(store)
    observe(store, row, "90")
    directory, manifest = retention.backup_database(store.path)
    observe(store, row, "91")
    with store.connect() as db:
        watermark = db.execute("SELECT MAX(first_seq) FROM tweet_ledger").fetchone()[0]
        expiry = db.execute("SELECT MAX(expires_at_ms) FROM tweet_ledger").fetchone()[0]
    with pytest.raises(ValueError):
        retention.restore(
            directory, tmp_path / "bad/tracking/tracking.db", store.path, expected_watermark=watermark + 1
        )
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry + 1)
    restored = tmp_path / "new/tracking/tracking.db"
    result = retention.restore(directory, restored, store.path, expected_watermark=watermark)
    assert result["restored"] and result["ledger_high_water"] == watermark
    recovered = Store(restored)
    assert make_page(recovered)["items"] == []
    assert not observe(recovered, recovered.get(row["project_id"]), "91")
    with recovered.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tweet_ledger").fetchone()[0] == 2
    backup_file = directory / "tracking.db"
    with backup_file.open("ab") as file:
        file.write(b"corruption")
    with pytest.raises(ValueError, match="hash"):
        retention.backup_info(directory)


def test_internal_feed_strict_permission_and_closed_source_health(cfg, store):
    cfg = __import__("dataclasses").replace(cfg, remote_enabled=False, dedicated_account=False)
    with TestClient(create_app(cfg, store)) as client:
        health = client.get("/health/ready").json()["data"]
        assert health["external_collection_enabled"] is False and health["source_state"] == "unconfigured"
        path = "/internal/v1/feed/bases"
        value = {"schema_version": 1, "actor": ACTOR, "profile": "published-v1", "query": QUERY}
        assert client.post(path, json=value).status_code == 401
        headers = {"authorization": "Bearer b3-tracking-direction-credential-xxxxxxxx"}
        assert client.post(path, headers=headers, json=value).status_code == 200
        assert (
            client.post(
                path, headers=headers, json=value | {"actor": ACTOR | {"tenant_id": "wrong"}}
            ).status_code
            == 422
        )
        assert client.post(path, headers=headers, json=value | {"schema_version": True}).status_code == 422
        assert client.post(path, headers=headers, json=value | {"ratings": []}).status_code == 422


@pytest.mark.parametrize(
    "boundary", ["after_copy", "after_inactivate", "after_ledger", "after_cleanup", "before_activate"]
)
def test_restore_every_pre_activation_commit_refuses_runtime_and_replay(store, tmp_path, boundary):
    row = target(store)
    observe(store, row, "900")
    directory, manifest = retention.backup_database(store.path)
    observe(store, row, "901")
    with store.connect() as db:
        watermark = db.execute("SELECT MAX(first_seq) FROM tweet_ledger").fetchone()[0]
    destination = tmp_path / boundary / "tracking/tracking.db"
    with pytest.raises(RuntimeError, match="restore interruption"):
        retention.restore(directory, destination, store.path, expected_watermark=watermark, fault=boundary)
    with pytest.raises(ValueError):
        Store(destination)
    with pytest.raises(ValueError):
        inspect(destination)
    with sqlite3.connect(destination) as db:
        if boundary != "after_copy":
            assert db.execute("SELECT recovery_ready FROM feed_meta").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 0


def test_activated_restore_has_full_horizon_no_created_replay_or_old_sse_anchor(store, cfg, tmp_path):
    row = target(store)
    observe(store, row, "910")
    with store.connect() as db:
        anchor = db.execute("SELECT event_id FROM changes LIMIT 1").fetchone()[0]
    directory, manifest = retention.backup_database(store.path)
    observe(store, row, "911")
    destination = tmp_path / "final/tracking/tracking.db"
    with pytest.raises(RuntimeError, match="after_activate"):
        retention.restore(directory, destination, store.path, expected_watermark=2, fault="after_activate")
    recovered = Store(destination)
    assert observe(recovered, recovered.get(row["project_id"]), "911")
    with recovered.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tweet_ledger").fetchone()[0] == 2
        assert (
            db.execute(
                "SELECT COUNT(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'"
            ).fetchone()[0]
            == 0
        )
    import dataclasses

    client = TestClient(create_app(dataclasses.replace(cfg, db_path=destination), recovered))
    response = client.get(
        "/internal/v1/events",
        headers={
            "authorization": "Bearer b3-tracking-direction-credential-xxxxxxxx",
            "last-event-id": anchor,
        },
    )
    assert response.status_code == 422
    with pytest.raises(ValueError, match="own ledger authority"):
        retention.restore(directory, tmp_path / "self/tracking/tracking.db", directory, expected_watermark=1)


def test_atomic_retention_high_water_survives_autocommit_interleavings_and_old_gets(store, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    row = target(store)
    observe(store, row, "920")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]

    def advance(value):
        with store.connect() as db:
            return retention.retention_now(db, value)

    values = [expiry, expiry - 100, expiry + 100, expiry - 10000] * 20
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(advance, values))
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry - 10000)
    with store.connect() as db:
        assert retention.retention_now(db) == expiry + 100
    assert store.latest() == [] and store.activities() == []
    from tracking.views import page

    assert page(store, "latest", {})["items"] == []
    assert page(store, "activities", {})["items"] == []


async def test_expired_sse_payload_stays_hidden_after_clock_rollback(store, cfg, monkeypatch):
    import asyncio

    row = target(store)
    observe(store, row, "930", text="must never reappear")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]
        retention.retention_now(db, expiry)
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry - 10000)
    app = create_app(cfg, store)
    body = []
    sent = asyncio.Event()

    async def receive():
        await asyncio.sleep(0.005)
        return (
            {"type": "http.disconnect"}
            if sent.is_set()
            else {"type": "http.request", "body": b"", "more_body": False}
        )

    async def send(message):
        if message["type"] == "http.response.body":
            body.append(message.get("body", b""))
            sent.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/internal/v1/events",
        "raw_path": b"/internal/v1/events",
        "query_string": b"",
        "headers": [(b"authorization", b"Bearer b3-tracking-direction-credential-xxxxxxxx")],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 2),
    }
    await asyncio.wait_for(app(scope, receive, send), 2)
    assert b"must never reappear" not in b"".join(body)
    assert b"heartbeat" in b"".join(body)


def test_stale_backup_cannot_restore_older_commands_notes_or_subscription_controls(store, tmp_path):
    row = target(store)
    observe(store, row, "940")
    directory, manifest = retention.backup_database(store.path)
    store.mutate(
        "update",
        row["project_id"],
        {"expected_revision": row["revision"], "notes": "new human-confirmed notes"},
        "owner",
        "change-after-backup",
    )
    destination = tmp_path / "stale/tracking/tracking.db"
    with pytest.raises(ValueError, match="stale control state"):
        retention.restore(directory, destination, store.path, expected_watermark=1)
    assert not destination.exists()


def test_one_verified_backup_covers_multiple_bounded_delete_batches(store, monkeypatch):
    row = target(store)
    now = retention.wall_ms()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for i in range(1001):
            identifier = str(100000 + i)
            db.execute(
                "INSERT INTO tweet_ledger(tweet_id,expires_at_ms,first_received_at_ms,origin_subscription_id,state) VALUES(?,?,?,?,'visible')",
                (identifier, now - 1, now - retention.TTL_MS, row["subscription_id"]),
            )
            db.execute(
                "INSERT INTO tweets(activity_id,project_id,subscription_id,handle,tweet_id,text,created_at,received_at,source,generation,tweet_kind,author_verified,type_evidence_version,expires_at_ms) VALUES(?,?,?,?,?,'expired batch content',1,1,'wss',1,'original',1,'fixture',?)",
                (
                    "act_" + str(uuid.uuid4()),
                    row["project_id"],
                    row["subscription_id"],
                    row["handle"],
                    identifier,
                    now - 1,
                ),
            )
        db.execute("COMMIT")
    calls = []

    def backup(*args, **kwargs):
        calls.append(1)
        return retention.backup_database(*args, **kwargs)

    result = retention.cleanup(store, backup=backup)
    assert result["deleted"] == 1001 and result["state"] == "completed" and len(calls) == 1
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tweets").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM tweet_ledger WHERE state='expired'").fetchone()[0] == 1001


def test_expired_receipt_payload_is_removed_but_reconcile_identifiers_remain(store, monkeypatch):
    row = target(store)
    observe(store, row, "950", text="expired receipt body")
    with store.connect() as db:
        expiry = db.execute("SELECT expires_at_ms FROM tweet_ledger").fetchone()[0]
        db.execute(
            "UPDATE tracking_outbox SET receipt=?",
            (json.dumps({"receipt_id": "fixture-receipt", "payload": {"text": "expired receipt body"}}),),
        )
    monkeypatch.setattr(retention, "wall_ms", lambda: expiry)
    assert retention.cleanup(store)["state"] == "completed"
    with store.connect() as db:
        receipt, original = db.execute("SELECT receipt,original_receipt_hash FROM tracking_outbox").fetchone()
        assert json.loads(receipt) == {"receipt_id": "fixture-receipt"} and len(original) == 64


def view_page(store, view, *, actor=None, **query):
    actor = actor or ACTOR
    base = feed.basis(
        store,
        feed.BasisRequest.model_validate(
            {
                "schema_version": 1,
                "actor": actor,
                "profile": "published-v1",
                "query": QUERY | query,
                "query_view_id": view,
            }
        ),
    )
    result = feed.snapshot(
        store,
        feed.SnapshotRequest.model_validate(
            {
                "schema_version": 1,
                "actor": actor,
                "basis_id": base["basis_id"],
                "query_hash": base["query_hash"],
                "limit": 1,
                "ratings_snapshot": project_ratings(base),
            }
        ),
    )
    return result


def test_same_view_ten_refreshes_live_arrivals_and_filters_do_not_self_exhaust(store):
    row = target(store)
    view = "qv1_" + str(uuid.uuid4())
    observe(store, row, "960")
    observe(store, row, "961")
    previous = view_page(store, view)
    for index in range(10):
        observe(store, row, str(1000 + index), text="burst " + str(index))
        result = view_page(
            store, view, q="" if index % 2 == 0 else "burst", ratings=["A"] if index % 3 else ["S", "A", "B"]
        )
        assert result["snapshot"]["snapshot_id"] != previous["snapshot"]["snapshot_id"]
        previous = result
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM feed_snapshots").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM feed_bases").fetchone()[0] == 0


def test_view_reclaim_is_scoped_to_actor_and_tab_and_pages_do_not_reclaim(store):
    row = target(store)
    for identifier in ("970", "971", "972"):
        observe(store, row, identifier)
    view1 = "qv1_" + str(uuid.uuid4())
    view2 = "qv1_" + str(uuid.uuid4())
    other = ACTOR | {"user_id": "usr_other"}
    first = view_page(store, view1)
    second = view_page(store, view2)
    foreign = view_page(store, view1, actor=other)
    refreshed = view_page(store, view1, q="body")
    with pytest.raises(DomainError) as invalidated:
        next_page(store, first["next_cursor"], query_view_id=view1)
    assert invalidated.value.status == 409
    assert len(next_page(store, second["next_cursor"], query_view_id=view2, limit=1)["items"]) == 1
    assert len(next_page(store, foreign["next_cursor"], query_view_id=view1, actor=other)["items"]) == 2
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM feed_snapshots").fetchone()[0] == 3
    with pytest.raises(DomainError) as mismatch:
        next_page(store, refreshed["next_cursor"], query_view_id=view2)
    assert mismatch.value.status == 422


def test_reclaimed_basis_returns404_and_invalid_hint_has_no_cache_side_effect(cfg, store):
    view = "qv1_" + str(uuid.uuid4())
    value = {
        "schema_version": 1,
        "actor": ACTOR,
        "profile": "published-v1",
        "query": QUERY,
        "query_view_id": view,
    }
    old = feed.basis(store, feed.BasisRequest.model_validate(value))
    feed.basis(store, feed.BasisRequest.model_validate(value))
    with pytest.raises(DomainError) as missing:
        feed.snapshot(
            store,
            feed.SnapshotRequest.model_validate(
                {
                    "schema_version": 1,
                    "actor": ACTOR,
                    "basis_id": old["basis_id"],
                    "query_hash": old["query_hash"],
                    "limit": 2,
                    "ratings_snapshot": project_ratings(old),
                }
            ),
        )
    assert missing.value.status == 404
    with TestClient(create_app(cfg, store)) as client:
        response = client.post(
            "/internal/v1/feed/bases",
            headers={"authorization": "Bearer b3-tracking-direction-credential-xxxxxxxx"},
            json=value | {"query_view_id": "qv1_NOT_A_UUID"},
        )
        assert response.status_code == 422
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM feed_bases").fetchone()[0] == 1


def test_no_hint_cursor_shape_and_capacity_remain_compatible(store):
    import base64

    row = target(store)
    observe(store, row, "980")
    observe(store, row, "981")
    result = make_page(store, limit=1)
    raw = result["next_cursor"].split(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert "w" not in payload
    assert len(next_page(store, result["next_cursor"])["items"]) == 1
    for _ in range(7):
        make_page(store)
    with pytest.raises(DomainError) as exhausted:
        make_page(store)
    assert exhausted.value.status == 429


def test_removed_subscription_keeps_history_but_not_active_counts(store):
    from tracking import views
    row = target(store)
    observe(store, row, 880011, text='preserved after unsubscribe')
    before = make_page(store)
    assert before['matched_total'] == 1
    cmd = 'cmd_' + str(uuid.uuid4())
    with store.connect() as db:
        db.execute("INSERT INTO commands(command_id,body_hash,envelope,project_id,subscription_id,revision,state,created_at,updated_at,request_id) VALUES(?,?,?,?,?,1,'succeeded',0,0,'test')", (cmd,'a'*64,'{}',row['project_id'],row['subscription_id']))
        db.execute("UPDATE projects SET desired='removed',status='removed',remote_state='absent',active_command_id=? WHERE project_id=?", (cmd,row['project_id']))
    after = make_page(store)
    assert after['matched_total'] == 1
    assert after['items'][0]['text'] == 'preserved after unsubscribe'
    assert after['subscription_counts_by_rating'] == {'S':0,'A':0,'B':0}
    assert views.page(store,'subscriptions',{})['items'] == []
    assert len(views.page(store,'subscriptions',{'include_removed':'true'})['items']) == 1
    assert views.page(store,'latest',{})['items'][0]['text'] == 'preserved after unsubscribe'
