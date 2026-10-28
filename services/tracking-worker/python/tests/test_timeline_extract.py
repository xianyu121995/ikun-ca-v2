"""AI timeline extraction: parse times, gate confidence, dedup, and never resurrect a deletion."""
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tracking import gemini
from tracking.api import create_app
from tracking.events import normalize
from tracking.timeline_extract import (
    delete_entry,
    edit_entry,
    interpret,
    list_public,
    run_pass,
)
from test_feed_retention import observe, target

CREATED = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc).timestamp()
TOKEN = "b3-tracking-direction-credential-xxxxxxxx"


def enable(monkeypatch, tmp_path, on=True):
    path = tmp_path / "ai.json"
    path.write_text(json.dumps({"enabled": True, "api_key": "AIza" + "x" * 35, "timeline_extract": on}))
    monkeypatch.setenv("IKUN_AI_CONFIG", str(path))


def announce(iso="2026-11-02T12:00:00Z", **extra):
    body = {
        "announces": True,
        "event_type": "tge",
        "title": "TGE 开盘",
        "confidence": 0.91,
        "concrete": True,
        "schedule": {"kind": "absolute", "iso": iso},
    }
    body.update(extra)
    return body


def test_absolute_utc_and_shanghai_offsets():
    utc = interpret(announce("2026-11-01T23:30:00Z"), CREATED)
    assert utc["starts_at"] == "2026-11-01T23:30:00Z"
    assert utc["date"] == "2026-11-02" and utc["hour"] == "07" and utc["status"] == "confirmed"

    shanghai = interpret(announce("2026-11-02T20:00:00+08:00"), None)
    assert shanghai["starts_at"] == "2026-11-02T12:00:00Z"
    assert shanghai["date"] == "2026-11-02" and shanghai["hour"] == "20"

    dated = interpret(announce(schedule={"kind": "date", "date": "2026-11-01", "timezone": "Asia/Shanghai", "hour": None}), CREATED)
    assert dated["date"] == "2026-11-01" and dated["hour"] is None and dated["status"] == "estimated"
    assert dated["starts_at"] == "2026-11-01T04:00:00Z"

    clock = interpret(announce(schedule={"kind": "date", "date": "2026-11-01", "timezone": "UTC", "hour": 23, "minute": 0}), CREATED)
    assert clock["date"] == "2026-11-02" and clock["hour"] == "07" and clock["starts_at"] == "2026-11-01T23:00:00Z"


def test_relative_and_wall_clock_use_tweet_created_at():
    relative = interpret(announce(schedule={"kind": "relative", "seconds": 7200}), CREATED)
    assert relative["starts_at"] == "2026-10-28T12:00:00Z"
    assert relative["date"] == "2026-10-28" and relative["hour"] == "20"

    wall = interpret(
        announce(schedule={"kind": "wall", "day_offset": 1, "hour": 20, "minute": 0, "timezone": "UTC"}),
        CREATED,
    )
    assert wall["starts_at"] == "2026-10-29T20:00:00Z"
    assert wall["date"] == "2026-10-30" and wall["hour"] == "04"
    assert interpret(announce(schedule={"kind": "relative", "seconds": 7200}), None) is None
    assert interpret(announce("2026-11-02T20:00:00"), CREATED) is None


def test_vague_times_and_low_confidence_are_ignored():
    assert interpret(announce(concrete=False, schedule={"kind": "vague"}), CREATED) is None
    assert interpret(announce(schedule={"kind": "vague"}, title="即将上线"), CREATED) is None
    assert interpret(announce(confidence=0.79), CREATED) is None
    assert interpret(announce(confidence=True), CREATED) is None
    assert interpret(announce(confidence=1.01), CREATED) is None
    assert interpret(announce(announces=False), CREATED) is None
    kept = interpret(announce(confidence=0.8), CREATED)
    assert kept["status"] == "estimated" and kept["confidence"] == 0.8


def test_flag_off_does_not_call_ai(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "501", text="TGE on 2026-11-02 12:00 UTC")
    enable(monkeypatch, tmp_path, on=False)
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    assert run_pass(store, {}) == 0
    with store.connect() as db:
        assert list_public(db) == []


def test_each_tweet_is_analyzed_once_and_failures_retry(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "501", text="TGE 2026-11-02T12:00:00Z")
    enable(monkeypatch, tmp_path)
    calls = {"n": 0}

    def boom(prompt, **kw):
        calls["n"] += 1
        raise gemini.AIUnavailable("ai_codex_timeout")

    monkeypatch.setattr(gemini, "generate_json", boom)
    failures = {}
    assert run_pass(store, failures) == 0 and "501" in failures
    with store.connect() as db:
        assert db.execute("SELECT 1 FROM receipts WHERE key=?", ("tracking.timeline.analyze.v1:501",)).fetchone() is None
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: announce())
    assert run_pass(store, failures, now=time.time() + 120) == 1
    assert run_pass(store, {}) == 0
    assert calls["n"] == 1
    with store.connect() as db:
        items = list_public(db)
    assert len(items) == 1 and items[0]["source_tweet_id"] == "501" and items[0]["title"] == "TGE 开盘"


def test_dedup_reschedule_and_distinct_types(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "501", text="first tge")
    enable(monkeypatch, tmp_path)
    scripts = iter([
        announce("2026-11-02T12:00:00Z", title="TGE 开盘", confidence=0.9),
        announce("2026-11-02T13:00:00Z", title="另一个标题", confidence=0.9),
        announce("2026-11-04T12:00:00Z", title="TGE 改期", confidence=0.95),
        announce("2026-11-02T12:00:00Z", event_type="airdrop", title="空投快照", confidence=0.92),
    ])
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: next(scripts))
    assert run_pass(store, {}) == 1
    observe(store, row, "502", text="same tge")
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        items = list_public(db)
    assert len(items) == 1
    assert items[0]["title"] == "TGE 开盘" and items[0]["starts_at"] == "2026-11-02T12:00:00Z"
    assert items[0]["source_tweet_id"] == "502"
    first_id = items[0]["entry_id"]

    observe(store, row, "503", text="rescheduled tge")
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        items = list_public(db)
    assert len(items) == 1 and items[0]["entry_id"] == first_id
    assert items[0]["title"] == "TGE 改期" and items[0]["date"] == "2026-11-04" and items[0]["hour"] == "20"

    observe(store, row, "504", text="airdrop too")
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        items = list_public(db)
    assert {item["event_type"] for item in items} == {"tge", "airdrop"}
    assert len({item["entry_id"] for item in items}) == 2


def test_deleted_entry_is_not_resurrected_and_edit_locks_it(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "501", text="tge")
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: announce())
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        entry_id = list_public(db)[0]["entry_id"]
    edited = edit_entry(
        store,
        entry_id,
        {"date": "2026-11-03", "hour": "09", "title": "人工改成 9 时", "status": "confirmed"},
        "fixture-admin",
        str(uuid.uuid4()),
    )
    assert edited["date"] == "2026-11-03" and edited["hour"] == "09" and edited["title"] == "人工改成 9 时"
    observe(store, row, "502", text="later reschedule")
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: announce("2026-12-01T00:00:00Z", title="又改期"))
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        assert list_public(db)[0]["date"] == "2026-11-03"
        assert json.loads(db.execute("SELECT result FROM receipts WHERE key=?", ("tracking.timeline.analyze.v1:502",)).fetchone()[0])["applied"] == "locked"

    assert delete_entry(store, entry_id, "fixture-admin", str(uuid.uuid4())) == {"entry_id": entry_id, "deleted": True}
    observe(store, row, "503", text="try again")
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: announce("2026-11-08T00:00:00Z", title="不该回来"))
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        assert list_public(db) == []
        applied = json.loads(db.execute("SELECT result FROM receipts WHERE key=?", ("tracking.timeline.analyze.v1:503",)).fetchone()[0])["applied"]
    assert applied == "tombstone"
    assert run_pass(store, {}) == 0


def test_replies_are_skipped_and_quotes_are_sent_to_the_model(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "601", kind="reply", text="reply should not be analyzed")
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("reply")))
    assert run_pass(store, {}) == 0

    content = {
        "id": "602",
        "text": "see quoted announcement",
        "createdAt": time.time() - 30,
        "userScreenName": row["handle"],
        "isReply": False,
        "isQuote": True,
        "quotedStatus": {"id": "9001", "text": "Mainnet 2026-11-02T12:00:00Z", "userScreenName": row["handle"]},
    }
    item = normalize(content, row["handle"])
    assert item["tweet_kind"] == "quote" and store.insert_tweet(row, item, "wss")
    seen = {}

    def capture(prompt, **kw):
        seen["prompt"] = prompt
        return announce(event_type="mainnet", title="主网上线")

    monkeypatch.setattr(gemini, "generate_json", capture)
    assert run_pass(store, {}) == 1
    assert "Mainnet 2026-11-02T12:00:00Z" in seen["prompt"]
    with store.connect() as db:
        assert list_public(db)[0]["event_type"] == "mainnet"


def test_http_lists_edits_and_keeps_tombstone(cfg, store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "501", text="tge")
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: announce())
    assert run_pass(store, {}) == 1
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    with TestClient(create_app(cfg, store)) as client:
        listed = client.get("/internal/v1/timeline-events", headers=headers)
        assert listed.status_code == 200 and len(listed.json()["data"]["items"]) == 1
        entry_id = listed.json()["data"]["items"][0]["entry_id"]
        denied = client.request(
            "DELETE",
            "/internal/v1/timeline-events/" + entry_id,
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"actor": {"user_id": "reader", "tenant_id": "ikun-main", "role": "user"}},
        )
        assert denied.status_code == 403
        key = str(uuid.uuid4())
        actor = {"user_id": "fixture-admin", "tenant_id": "ikun-main", "role": "superadmin"}
        deleted = client.request(
            "DELETE",
            "/internal/v1/timeline-events/" + entry_id,
            headers={**headers, "Idempotency-Key": key},
            json={"actor": actor},
        )
        assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] is True
        again = client.request(
            "DELETE",
            "/internal/v1/timeline-events/" + entry_id,
            headers={**headers, "Idempotency-Key": key},
            json={"actor": actor},
        )
        assert again.status_code == 200 and again.json()["data"] == deleted.json()["data"]
        empty = client.get("/internal/v1/timeline-events", headers=headers)
        assert empty.json()["data"]["items"] == []
    observe(store, row, "502", text="again")
    assert run_pass(store, {}) == 1
    with store.connect() as db:
        assert list_public(db) == []
