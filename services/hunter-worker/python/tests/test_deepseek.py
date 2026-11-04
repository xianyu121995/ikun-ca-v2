"""DeepSeek provider: mocked chat completions, no live API calls."""
import json
import logging
import subprocess

import httpx
import pytest

from conftest import NOW, discover
from hunterradar import ai_prefill, gemini
from hunterradar.formal import FormalService

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
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com/v1",
        "timeout": 12,
    })
    env_key = "sk-" + "e" * 40
    monkeypatch.setenv("DEEPSEEK_API_KEY", env_key)
    seen = scripted(monkeypatch, lambda url, headers, body: deepseek_response({"name": "深"}))
    value = gemini.generate_json("只输出 JSON")
    assert value == {"name": "深"}
    post = seen["posts"][0]
    assert post["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert post["json"]["model"] == "deepseek-flash"
    assert post["json"]["thinking"] == {"type": "disabled"}
    assert post["json"]["response_format"] == {"type": "json_object"}
    assert post["json"]["messages"] == [{"role": "user", "content": "只输出 JSON"}]
    assert post["headers"]["Authorization"] == "Bearer " + env_key
    assert seen["init"]["timeout"] == 12
    assert env_key not in post["url"]


def test_fenced_content_parses_and_key_stays_out_of_errors(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "deepseek_api_key": KEY})
    scripted(monkeypatch, lambda url, headers, body: httpx.Response(
        200, json={"choices": [{"message": {"content": "```json\n{\"name\": \"围栏\"}\n```"}}]},
    ))
    assert gemini.generate_json("p") == {"name": "围栏"}
    assert gemini.settings()["api_key"] == KEY

    def fail(url, headers, body):
        return httpx.Response(500, text=KEY)

    scripted(monkeypatch, fail)
    with pytest.raises(gemini.AIUnavailable) as exc:
        gemini.generate_json("p")
    assert str(exc.value) == "ai_http_500" and KEY not in str(exc.value)


def test_timeout_falls_back_to_codex_and_logs(tmp_path, monkeypatch, caplog):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "api_key": KEY,
        "codex_bin": "/bin/true",
    })
    assert gemini.settings()["fallback"]["provider"] == "codex"

    def fail(url, headers, body):
        raise httpx.TimeoutException("timed out")

    scripted(monkeypatch, fail)

    def fake_run(args, cwd, env, **kwargs):
        out = args[args.index("-o") + 1]
        open(out, "w").write('{"name": "回退"}')
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with caplog.at_level(logging.WARNING, logger="hunterradar.gemini"):
        value = gemini.generate_json("prompt")
    assert value == {"name": "回退"}
    assert "deepseek_fallback code=ai_deepseek_timeout to=codex" in caplog.text
    assert KEY not in caplog.text


def test_http_error_falls_back_to_gemini(tmp_path, monkeypatch, caplog):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "deepseek_api_key": KEY,
        "api_key": GEMINI_KEY,
        "fallback_provider": "gemini",
        "gemini_model": "gemini-2.5-flash",
    })

    def route(url, headers, body):
        if "deepseek.com" in url:
            return httpx.Response(503, text="down")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}]})

    seen = scripted(monkeypatch, route)
    with caplog.at_level(logging.WARNING, logger="hunterradar.gemini"):
        assert gemini.generate_json("prompt") == {"ok": True}
    assert "deepseek.com" in seen["posts"][0]["url"]
    assert "gemini-2.5-flash" in seen["posts"][1]["url"]
    assert seen["posts"][1]["headers"]["x-goog-api-key"] == GEMINI_KEY
    assert "deepseek_fallback code=ai_http_503 to=gemini" in caplog.text


def test_fallback_none_does_not_call_codex(tmp_path, monkeypatch):
    write_cfg(tmp_path, monkeypatch, {
        "enabled": True,
        "provider": "deepseek",
        "api_key": KEY,
        "fallback_provider": "none",
        "codex_bin": "/bin/true",
    })
    scripted(monkeypatch, lambda url, headers, body: httpx.Response(429, json={"error": "busy"}))

    def unexpected(*args, **kwargs):
        raise AssertionError("codex")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(gemini.AIUnavailable, match="ai_rate_limited"):
        gemini.generate_json("p")
    assert not gemini.cooling()


def test_prefill_uses_deepseek_body(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)["discovery_id"], NOW)
    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek"})
    assert ai_prefill.run_pass(store, {}) == 0

    write_cfg(tmp_path, monkeypatch, {"enabled": True, "provider": "deepseek", "api_key": KEY, "model": "deepseek-flash"})
    payload = {"name": "SOL上的AI审计发射台", "website": "", "description": "简介", "notes": "", "category": "", "rating": "A", "rating_reason": "推文写了测试网进展。"}
    seen = scripted(monkeypatch, lambda url, headers, body: deepseek_response(payload))
    monkeypatch.setattr(
        FormalService, "page",
        lambda self, kind, query, now=None: {"items": [dto | {"profile_bio": "AI audits"}], "next_cursor": None},
    )
    assert ai_prefill.run_pass(store, {}) == 1
    body = seen["posts"][0]["json"]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert "预填" in body["messages"][0]["content"]
    current = FormalService(store).discovery(dto["discovery_id"], NOW)
    assert current["ai_suggestion"]["name"] == "SOL上的AI审计发射台"
    assert current["ai_suggestion"]["rating"] == "A" and current["project"]["rating"] == "A"
