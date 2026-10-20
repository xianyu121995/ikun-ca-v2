import importlib.util
import json
import time
from pathlib import Path

from test_feed_retention import make_page, observe, target

spec = importlib.util.spec_from_file_location("restore_tracking_types", Path(__file__).resolve().parents[4]/"release-integration/scripts/restore_tracking_types.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def test_saved_wss_type_restored_idempotently_without_voice_or_subscription_changes(store):
    row = target(store)
    observe(store,row,"991",kind="quote")
    observe(store,row,"992",kind="unknown")
    observe(store,row,"993",kind="repost")
    with store.connect() as db:
        db.execute("UPDATE tweets SET tweet_kind='unknown',type_evidence_version='conflicting-structured-v1' WHERE tweet_id='991'")
        before = [tuple(r) for r in db.execute("SELECT * FROM projects")]
        created = db.execute("SELECT count(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'").fetchone()[0]
        plan = repair.restore(db,time.time()-60)
        assert plan["restored"][0]["kind"] == "quote"
        assert db.execute("SELECT tweet_kind FROM tweets WHERE tweet_id='991'").fetchone()[0] == "unknown"
        assert len(repair.restore(db,time.time()-60,apply=True)["restored"]) == 1
        assert repair.restore(db,time.time()-60,apply=True)["restored"] == []
        assert [tuple(r) for r in db.execute("SELECT * FROM projects")] == before
        assert db.execute("SELECT count(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'").fetchone()[0] == created
        event = json.loads(db.execute("SELECT data FROM changes WHERE event_type='tracking.feed.activity.updated.v1' ORDER BY seq DESC").fetchone()[0])
        assert event["is_live_new"] is False and event["replay"] is True
    assert {r["tweet_id"] for r in make_page(store,limit=10)["items"]} == {"991","992"}


def test_quote_receipt_recovery_and_protected_account_untouched(store):
    row = target(store)
    observe(store,row,"994",kind="unknown")
    with store.connect() as db:
        db.execute("INSERT INTO receipts(key,fingerprint,result,at) VALUES(?,?,?,?)",('tracking.quote.v1:994','fixture',json.dumps({"tweet_id":"995","text":"fixture quote","author_handle":"fixture_author"}),time.time()))
        assert repair.restore(db,time.time()-60)["restored"][0]["evidence"] == "saved_quote_receipt"
        db.execute("UPDATE tweets SET handle='tampad_' WHERE tweet_id='994'")
        assert repair.restore(db,time.time()-60,apply=True)["restored"] == []
        assert db.execute("SELECT tweet_kind FROM tweets WHERE tweet_id='994'").fetchone()[0] == "unknown"
