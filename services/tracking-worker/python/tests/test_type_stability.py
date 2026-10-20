import json
import time

import pytest
from conftest import tweet
from test_feed_retention import make_page, target

from tracking.events import normalize
from tracking.views import page


def payload(row, identifier="901", kind="original", **extra):
    value = normalize(tweet(row["handle"], identifier, at=time.time() - 1, **extra), row["handle"])
    value["tweet_kind"] = kind
    return value


@pytest.mark.parametrize("kind", ["original", "quote", "reply", "repost"])
@pytest.mark.parametrize("source", ["wss", "rest"])
def test_known_type_never_degrades_on_unknown_or_conflict(store, kind, source):
    row = target(store)
    initial = payload(row, kind=kind)
    assert store.insert_tweet(row, initial, "wss")
    uncertain = initial | {"tweet_kind": "unknown", "type_evidence_version": "conflicting-structured-v1"}
    assert not store.insert_tweet(row, uncertain, source)
    with store.connect() as db:
        assert db.execute("SELECT tweet_kind FROM tweets").fetchone()[0] == kind


def test_rest_and_generic_wss_cannot_override_quote_but_explicit_live_evidence_can(store):
    row = target(store)
    quote = normalize(tweet(row["handle"], "902", at=time.time()-1, isQuote=True), row["handle"])
    assert store.insert_tweet(row, quote, "wss")
    rest = normalize(tweet(row["handle"], "902", at=time.time()-1, isRetweet=False), row["handle"],
                     event_type="REST_USER_TWEETS_NO_RETWEETS")
    assert rest["tweet_kind"] == "original"
    assert not store.insert_tweet(row, rest, "rest")
    generic = normalize(tweet(row["handle"], "902", at=time.time()-1), row["handle"])
    assert not store.insert_tweet(row, generic, "wss")
    reply = normalize(tweet(row["handle"], "902", at=time.time()-1, isReply=True), row["handle"])
    assert store.insert_tweet(row, reply, "wss")
    assert make_page(store)["items"] == []
    with store.connect() as db:
        assert db.execute("SELECT tweet_kind FROM tweets").fetchone()[0] == "reply"


def test_unknown_generation_enrichment_retains_known_type_without_second_voice_event(store):
    row = target(store)
    assert store.insert_tweet(row, payload(row, "903", "quote", isQuote=True), "wss")
    with store.connect() as db:
        db.execute("UPDATE projects SET generation=generation+1 WHERE project_id=?", (row["project_id"],))
    row = store.get(row["project_id"])
    assert store.insert_tweet(row, payload(row, "903", "unknown"), "rest")
    assert make_page(store)["items"][0]["tweet_kind"] == "quote"
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM changes WHERE event_type='tracking.feed.activity.created.v1'").fetchone()[0] == 1


def test_unknown_visible_in_both_latest_profiles_but_never_voice_and_reposts_still_filtered(store):
    row = target(store)
    assert store.insert_tweet(row, payload(row, "904", "unknown"), "wss")
    assert store.insert_tweet(row, payload(row, "905", "repost"), "wss")
    assert [r["tweet_id"] for r in make_page(store)["items"]] == ["904"]
    assert [r["tweet_id"] for r in page(store, "latest", {"limit": "50"})["items"]] == ["904"]
    with store.connect() as db:
        events = [dict(r) for r in db.execute("SELECT * FROM changes WHERE event_type LIKE 'tracking.feed.%'")]
    assert len(events) == 1
    assert events[0]["event_type"] == "tracking.feed.activity.updated.v1"
    value = json.loads(events[0]["data"])
    assert value["replay"] is True and value["is_live_new"] is False


def test_unknown_can_keep_structured_quote_context_without_guessing_type(store):
    row = target(store)
    unknown = normalize(tweet(row["handle"], "906", at=time.time()-1, isQuote="bad",
                              quotedStatus={"id":"907", "userScreenName":"fixture_author", "text":"quoted fixture"}), row["handle"])
    assert unknown["tweet_kind"] == "unknown"
    assert store.insert_tweet(row, unknown, "wss")
    item = make_page(store)["items"][0]
    assert item["tweet_kind"] == "unknown" and item["quoted_tweet"]["text"] == "quoted fixture"
