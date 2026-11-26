"""Official filtered-stream rules and post mapping. No live X calls."""
import json
import time

import httpx
import pytest
from conftest import add

from tracking.remote import Remote
from tracking.xstream import STREAM_QUERY, parse_stream_post


def x_post(tweet_id, text, username="project1", *, quoted=None, reply=False, retweet=False, note=None):
    data = {
        "id": tweet_id,
        "text": text,
        "author_id": "100",
        "created_at": time.time(),
        "edit_history_tweet_ids": [tweet_id],
    }
    if note:
        data["note_tweet"] = {"text": note}
    users = [{"id": "100", "username": username, "name": "Project"}]
    if quoted:
        data["referenced_tweets"] = [{"type": "quoted", "id": quoted["id"]}]
        users.append({"id": "200", "username": quoted["username"], "name": quoted.get("name", quoted["username"])})
        quoted_post = {"id": quoted["id"], "text": quoted["text"], "author_id": "200"}
    else:
        quoted_post = None
    if reply:
        data["referenced_tweets"] = [{"type": "replied_to", "id": "9"}]
        data["in_reply_to_user_id"] = "9"
    if retweet:
        data["referenced_tweets"] = [{"type": "retweeted", "id": "8"}]
    includes = {"users": users}
    if quoted_post:
        includes["tweets"] = [quoted_post]
    return {
        "data": data,
        "includes": includes,
        "matching_rules": [{"id": "1", "tag": f"ikun-ca-v2:tracking:{username}"}],
    }


async def test_reconcile_adds_and_deletes_account_rules_without_backfill(worker, store, vendor):
    add(store)
    await worker.reconcile()
    added = [body for name, body in vendor.calls if name == "rules_add"]
    assert added == [
        {"add": [{"value": "from:project1 -is:retweet -is:reply", "tag": "ikun-ca-v2:tracking:project1"}]}
    ]
    assert "backfill_minutes" not in json.dumps(vendor.calls)
    assert "backfill_minutes" not in STREAM_QUERY
    payload = x_post("555", "short", note="full official post text")
    assert worker.ingest(payload)
    assert store.activities()[0]["tweet_kind"] == "original"
    assert store.activities()[0]["text"] == "full official post text"
    assert store.activities()[0]["source"] == "wss"
    rule_id = vendor.rows["project1"]["id"]
    row = store.get("prj_550e8400-e29b-41d4-a716-446655440001")
    store.mutate("remove", row["project_id"], {"expected_revision": row["revision"]}, "admin", "remove-x")
    await worker.reconcile()
    assert "project1" not in vendor.rows
    deleted = [body for name, body in vendor.calls if name == "rules_delete"]
    assert deleted[-1] == {"delete": {"ids": [rule_id]}}
    with store.connect() as db:
        assert db.execute("SELECT text FROM tweets WHERE tweet_id='555'").fetchone()[0] == "full official post text"


def test_stream_original_and_quote_enter_the_existing_ingest_path(worker, store):
    row = add(store)
    store.observe(row, claim="owned", status="running", remote_state="active", baseline_ready=1)
    original = x_post("701", "an original post")
    quote = x_post(
        "702",
        "quoting them",
        quoted={"id": "700", "text": "the quoted post", "username": "otherauthor", "name": "Other"},
    )
    assert worker.ingest(original)
    assert worker.ingest(quote)
    assert worker.ingest(x_post("703", "a reply", reply=True)) is False
    assert worker.ingest(x_post("704", "a repost", retweet=True)) is False
    kinds = {item["tweet_id"]: item["tweet_kind"] for item in store.activities()}
    assert kinds == {"701": "original", "702": "quote"}
    with store.connect() as db:
        saved = db.execute("SELECT result FROM receipts WHERE key='tracking.quote.v1:702'").fetchone()
    context = json.loads(saved[0])
    assert context["author_handle"] == "otherauthor"
    assert context["text"] == "the quoted post"
    assert parse_stream_post(original)[1]["type_evidence_version"] == "x-stream-structured-v1"
    assert parse_stream_post(quote)[1]["tweet_kind"] == "quote"


async def test_rules_request_sends_bearer_header_and_not_the_token_in_the_url(cfg):
    seen = []

    def transport(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer " + cfg.secret("token")
        assert cfg.secret("token") not in str(request.url)
        assert "backfill_minutes" not in str(request.url)
        return httpx.Response(200, json={"data": [], "meta": {"result_count": 0}})

    remote = Remote(cfg, transport=httpx.MockTransport(transport))
    try:
        assert await remote.watches() == {}
    finally:
        await remote.close()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/2/tweets/search/stream/rules"


@pytest.mark.parametrize("kind", ["reply", "retweet"])
def test_excluded_stream_posts_do_not_normalize(kind):
    payload = x_post("800", "skip", reply=kind == "reply", retweet=kind == "retweet")
    assert parse_stream_post(payload) is None
