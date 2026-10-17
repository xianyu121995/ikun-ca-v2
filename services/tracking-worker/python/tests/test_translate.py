"""Owner decision 2026-10-18: tweets are pushed first; Chinese translation is added afterwards."""
import json

from conftest import tweet
from test_feed_retention import make_page, target
from tracking import gemini, translate
from tracking.events import normalize


def test_translation_added_after_push_and_failures_never_block(store, monkeypatch, tmp_path):
    row = target(store)
    assert store.insert_tweet(row, normalize(tweet(row["handle"], "77", text="gm, mainnet soon $ABC"), "project1"), "wss")
    first = make_page(store)["items"][0]
    assert first["text"] == "gm, mainnet soon $ABC" and first["translation_zh"] is None

    # No config: nothing happens, nothing raises.
    monkeypatch.setenv("IKUN_AI_CONFIG", str(tmp_path / "missing.json"))
    assert translate.run_pass(store, {}) == 0

    config = tmp_path / "ai.json"
    config.write_text(json.dumps({"enabled": True, "api_key": "AIza" + "x" * 35}))
    monkeypatch.setenv("IKUN_AI_CONFIG", str(config))
    failures = {}
    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: (_ for _ in ()).throw(gemini.AIUnavailable("ai_http_500")))
    assert translate.run_pass(store, failures) == 0 and "77" in failures
    assert make_page(store)["items"][0]["translation_zh"] is None

    monkeypatch.setattr(gemini, "generate_json", lambda prompt, **kw: {"text": "早上好，主网即将上线 $ABC", "quote": None})
    assert translate.run_pass(store, {}) == 1
    assert make_page(store)["items"][0]["translation_zh"] == {"text": "早上好，主网即将上线 $ABC", "quote": None}
    assert translate.run_pass(store, {}) == 0  # already translated


def test_chinese_tweets_are_skipped_without_calling_ai(store, monkeypatch, tmp_path):
    row = target(store)
    assert store.insert_tweet(row, normalize(tweet(row["handle"], "78", text="今天主网上线了"), "project1"), "wss")
    config = tmp_path / "ai.json"
    config.write_text(json.dumps({"enabled": True, "api_key": "AIza" + "x" * 35}))
    monkeypatch.setenv("IKUN_AI_CONFIG", str(config))
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    assert translate.run_pass(store, {}) == 1
    assert make_page(store)["items"][0]["translation_zh"] is None
