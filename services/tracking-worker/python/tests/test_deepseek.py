"""DeepSeek provider: mocked chat completions, no live API calls."""
import json
import logging
import subprocess

import httpx
import pytest

from test_feed_retention import observe, target
from tracking import gemini, translate
from tracking.events import normalize
from tracking.timeline_extract import list_public, run_pass
from conftest import tweet

KEY = "sk-" + "a" * 32
GEMINI_KEY = "AIza" + "b" * 32


@pytest.fixture(autouse=True)
def _clear_deepseek_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def write_cfg(tmp_path, monkeypatch, payload):
    path = tmp_path / "ai.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv("IKUN_AI_CONFIG", str(path))
    return path


def scripted(monkeypatch, handler):
    seen = {"posts": []}

    class Client:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            seen["posts"].append({"url": url, "headers": headers, "json": json})
            return handler(url, headers, json)

    monkeypatch.setattr(gemini.httpx, "Client", Client)
    return seen


def deepseek_response(payload):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})


def test_defaults_model_base_url_and_missing_key(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "api_key": KEY})
    cfg = gemini.settings()
    assert cfg["provider"] == "deepseek"
    assert cfg["model"] == "deepseek-flash"
    assert cfg["base_url"] == "https://api.deepseek.com"
    assert cfg["timeout"] is None
    assert cfg["fallback"] is None
    assert gemini.enabled()

    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "codex_bin": "/bin/true"})
    assert gemini.settings() is None and not gemini.enabled()
    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("must not call")

    monkeypatch.setattr(gemini.httpx, "Client", boom)
    with pytest.raises(gemini.AIUnavailable, match="ai_not_configured"):
        gemini.generate_json("prompt")
    assert called["n"] == 0


def test_env_key_and_request_shape(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "timeout": 18,
    })
    env_key = "sk-" + "e" * 40
    monkeypatch.setenv("DEEPSEEK_API_KEY", env_key)
    seen = scripted(monkeypatch, lambda url, headers, body: deepseek_response({"text": "你好"}))
    assert gemini.generate_json("翻译") == {"text": "你好"}
    post = seen["posts"][0]
    assert post["url"] == "https://api.deepseek.com/chat/completions"
    assert post["json"]["model"] == "deepseek-flash"
    assert post["json"]["thinking"] == {"type": "disabled"}
    assert post["json"]["response_format"] == {"type": "json_object"}
    assert post["headers"]["Authorization"] == "Bearer " + env_key
    assert seen["init"]["timeout"] == 18
    assert env_key not in post["url"]


def test_fenced_content_parses_and_key_stays_out_of_errors(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "deepseek_api_key": KEY})
    scripted(monkeypatch, lambda url, headers, body: httpx.Response(
        200, json={"choices": [{"message": {"content": "```json\n{\"text\": \"围栏\"}\n```"}}]},
    ))
    assert gemini.generate_json("p") == {"text": "围栏"}

    scripted(monkeypatch, lambda url, headers, body: httpx.Response(500, text=KEY))
    with pytest.raises(gemini.AIUnavailable) as exc:
        gemini.generate_json("p")
    assert str(exc.value) == "ai_http_500" and KEY not in str(exc.value)


def test_timeout_falls_back_to_codex_and_logs(tmp_path, monkeypatch, caplog):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "api_key": KEY,
        "fallback_provider": "codex",
        "codex_bin": "/bin/true",
    })

    def fail(url, headers, body):
        raise httpx.TimeoutException("timed out")

    scripted(monkeypatch, fail)

    def fake_run(args, cwd, env, **kwargs):
        out = args[args.index("-o") + 1]
        open(out, "w").write('{"text": "回退"}')
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with caplog.at_level(logging.WARNING, logger="tracking.gemini"):
        value = gemini.generate_json("prompt")
    assert value == {"text": "回退"}
    assert "deepseek_fallback code=ai_deepseek_timeout to=codex" in caplog.text
    assert KEY not in caplog.text


def test_network_error_falls_back_to_gemini(tmp_path, monkeypatch, caplog):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "deepseek_api_key": KEY,
        "gemini_api_key": GEMINI_KEY,
        "fallback_provider": "gemini",
        "gemini_model": "gemini-2.5-flash",
    })
    calls = {"n": 0}

    def route(url, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}]})

    seen = scripted(monkeypatch, route)
    with caplog.at_level(logging.WARNING, logger="tracking.gemini"):
        assert gemini.generate_json("prompt") == {"ok": True}
    assert "gemini-2.5-flash" in seen["posts"][1]["url"]
    assert "deepseek_fallback code=ai_network to=gemini" in caplog.text


def test_fallback_none_does_not_call_codex(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "api_key": KEY,
        "fallback_provider": "none",
        "codex_bin": "/bin/true",
    })
    def fail(url, headers, body):
        raise httpx.TimeoutException("timed out")

    scripted(monkeypatch, fail)

    def unexpected(*args, **kwargs):
        raise AssertionError("codex")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(gemini.AIUnavailable, match="ai_deepseek_timeout"):
        gemini.generate_json("p")


def test_translate_uses_deepseek(store, monkeypatch, tmp_path):
    row = target(store)
    assert store.insert_tweet(row, normalize(tweet(row["handle"], "91", text="gm, mainnet soon $ABC"), "project1"), "wss")
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek"})
    assert translate.run_pass(store, {}) == 0

    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "api_key": KEY})
    payload = {"text": "早上好，主网即将上线 $ABC", "quote": None}
    seen = scripted(monkeypatch, lambda url, headers, body: deepseek_response(payload))
    assert translate.run_pass(store, {}) == 1
    body = seen["posts"][0]["json"]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert "翻译" in body["messages"][0]["content"]
    from test_feed_retention import make_page
    assert make_page(store)["items"][0]["translation_zh"] == payload


def test_timeline_uses_deepseek(store, monkeypatch, tmp_path):
    row = target(store)
    observe(store, row, "901", text="TGE on 2026-11-02 12:00 UTC")
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "timeline_extract": True})
    assert run_pass(store, {}) == 0

    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "api_key": KEY,
        "model": "deepseek-flash",
        "timeline_extract": True,
    })
    payload = {
        "announces": True,
        "event_type": "tge",
        "title": "TGE 开盘",
        "confidence": 0.91,
        "concrete": True,
        "schedule": {"kind": "absolute", "iso": "2026-11-02T12:00:00Z"},
    }
    seen = scripted(monkeypatch, lambda url, headers, body: deepseek_response(payload))
    assert run_pass(store, {}) == 1
    body = seen["posts"][0]["json"]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert "具体日期" in body["messages"][0]["content"]
    with store.connect() as db:
        items = list_public(db)
    assert len(items) == 1 and items[0]["title"] == "TGE 开盘"
