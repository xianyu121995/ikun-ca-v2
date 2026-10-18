"""Minimal Gemini client for ikun.ca (owner decision 2026-10-18).

The key lives only in the owner's local config file (default:
~/Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json, override with IKUN_AI_CONFIG):
  {"enabled": true, "provider": "gemini", "api_key": "AIza...", "model": "gemini-flash-latest",
   "proxy": "http://127.0.0.1:7897"}
The file is re-read on every call so the owner can change or remove the key without a restart.
Errors never include the key, request URL or response body.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
from pathlib import Path

import httpx

DEFAULT_PATH = Path.home() / "Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


FALLBACK_MODELS = ("gemini-flash-latest", "gemini-3.8-flash", "gemini-2.5-flash")
_WORKING = {"model": None}


class AIUnavailable(Exception):
    """Raised with a short code only (no secrets)."""


def settings():
    path = Path(os.environ.get("IKUN_AI_CONFIG") or DEFAULT_PATH)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("enabled") is False:
        return None
    proxy = data.get("proxy") if isinstance(data.get("proxy"), str) and re.fullmatch(r"(https?|socks5h?)://[A-Za-z0-9.\-]+:\d{1,5}", data.get("proxy")) else None
    if data.get("provider") == "codex":
        # Owner decision 2026-10-18: use the owner's ChatGPT Pro login through the official `codex exec` CLI.
        model = data.get("codex_model") if isinstance(data.get("codex_model"), str) and re.fullmatch(r"[A-Za-z0-9._\-]{1,80}", data.get("codex_model")) else None
        binary = data.get("codex_bin") if isinstance(data.get("codex_bin"), str) and data.get("codex_bin").startswith("/") else None
        return {"provider": "codex", "model": model, "proxy": proxy, "codex_bin": binary}
    key = data.get("api_key")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]{20,300}", key):
        return None
    model = data.get("model") if isinstance(data.get("model"), str) and re.fullmatch(r"[A-Za-z0-9._\-]{1,80}", data.get("model")) else "gemini-flash-latest"
    proxy = data.get("proxy") if isinstance(data.get("proxy"), str) and re.fullmatch(r"(https?|socks5h?)://[A-Za-z0-9.\-]+:\d{1,5}", data.get("proxy")) else None
    return {"provider": "gemini", "api_key": key, "model": model, "proxy": proxy}


def cooldown_path():
    cfg = Path(os.environ.get("IKUN_AI_CONFIG") or DEFAULT_PATH)
    return cfg.parent.parent / "ops/ai.cooldown.json"


def cooling():
    try:return json.loads(cooldown_path().read_text()).get('until', 0) > time.time()
    except (OSError, ValueError, TypeError):return False


def enabled():
    cfg = settings()
    return cfg is not None and (cfg["provider"] == "codex" or not cooling())


CODEX_CANDIDATES = ("/opt/homebrew/bin/codex", "/usr/local/bin/codex", "/Applications/Codex.app/Contents/Resources/codex",
                    "/Applications/ChatGPT.app/Contents/Resources/codex")


def codex_binary(cfg):
    import shutil
    for path in ([cfg.get("codex_bin")] if cfg.get("codex_bin") else []) + list(CODEX_CANDIDATES) + [shutil.which("codex") or ""]:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise AIUnavailable("ai_bad_output") from None
        try:
            value = json.loads(text[start:end + 1])
        except ValueError:
            raise AIUnavailable("ai_bad_output") from None
    if not isinstance(value, dict):
        raise AIUnavailable("ai_bad_output")
    return value


def codex_json(prompt: str, cfg, timeout: float = 240.0) -> dict:
    import subprocess
    import tempfile
    binary = codex_binary(cfg)
    if not binary:
        raise AIUnavailable("ai_codex_missing")
    home = str(Path.home())
    env = {"HOME": home, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "en_US.UTF-8"}
    if cfg.get("proxy"):
        env.update(HTTPS_PROXY=cfg["proxy"], HTTP_PROXY=cfg["proxy"], https_proxy=cfg["proxy"], http_proxy=cfg["proxy"])
    with tempfile.TemporaryDirectory(prefix="ikun-ai-") as work:
        out = os.path.join(work, "out.txt")
        args = [binary, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-o", out]
        if cfg.get("model"):
            args += ["-m", cfg["model"]]
        args.append(prompt + "\n\n只输出一个 JSON 对象，不要运行任何命令，不要输出其他文字。")
        try:
            done = subprocess.run(args, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AIUnavailable("ai_codex_timeout") from None
        except OSError:
            raise AIUnavailable("ai_codex_missing") from None
        if done.returncode != 0:
            err = done.stderr.decode("utf-8", "replace").lower()
            raise AIUnavailable("ai_rate_limited" if ("rate limit" in err or "usage limit" in err or "429" in err)
                                else "ai_key_rejected" if ("login" in err or "unauthorized" in err or "401" in err) else "ai_codex_failed")
        try:
            text = Path(out).read_text(encoding="utf-8")
        except OSError:
            text = done.stdout.decode("utf-8", "replace")
    return extract_json(text)


def generate_json(prompt: str, *, timeout: float = 25.0) -> dict:
    cfg = settings()
    if cfg is None:
        raise AIUnavailable("ai_not_configured")
    if cfg["provider"] == "codex":
        return codex_json(prompt, cfg)
    if cooling():raise AIUnavailable('ai_rate_limited')
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    headers = {"x-goog-api-key": cfg["api_key"], "content-type": "application/json"}
    # AI Studio now issues "AQ." auth keys as well as legacy "AIza" keys; both go in x-goog-api-key.
    models = [cfg["model"]] + [m for m in FALLBACK_MODELS if m != cfg["model"]]
    if _WORKING["model"] in models:
        models.remove(_WORKING["model"]); models.insert(0, _WORKING["model"])
    try:
        with httpx.Client(proxy=cfg["proxy"], verify=ssl.create_default_context(), timeout=timeout, trust_env=cfg["proxy"] is None) as client:
            for model in models:
                response = client.post(ENDPOINT.format(model=model), headers=headers, json=body)
                if response.status_code == 400 and "thinkingConfig" in body["generationConfig"]:
                    # Some models reject thinkingConfig; retry once without it.
                    body["generationConfig"].pop("thinkingConfig", None)
                    response = client.post(ENDPOINT.format(model=model), headers=headers, json=body)
                if response.status_code != 404:
                    if response.status_code == 200:
                        _WORKING["model"] = model
                    break
    except httpx.HTTPError:
        raise AIUnavailable("ai_network") from None
    if response.status_code == 429:
        delay = 300.0
        try:
            details = response.json().get('error', {}).get('details', [])
            for item in details:
                wait = item.get('retryDelay', '')
                if isinstance(wait, str) and re.fullmatch(r'[0-9.]+s', wait):delay = max(delay, float(wait[:-1]))
                if any('PerDay' in v.get('quotaId', '') for v in item.get('violations', [])):
                    delay = max(delay, (int(time.time()) // 86400 + 1) * 86400 - time.time() + 60)
        except (ValueError, TypeError):pass
        path = cooldown_path();path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:json.dump({'until':time.time()+delay, 'reason':'ai_rate_limited'}, out)
        os.replace(tmp, path)
        raise AIUnavailable("ai_rate_limited")
    if response.status_code in (401, 403):
        raise AIUnavailable("ai_key_rejected")
    if response.status_code != 200:
        raise AIUnavailable("ai_http_%d" % response.status_code)
    try:
        parts = response.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        value = json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIUnavailable("ai_bad_output") from None
    if not isinstance(value, dict):
        raise AIUnavailable("ai_bad_output")
    return value


def mostly_chinese(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    cjk = sum(1 for c in letters if "一" <= c <= "鿿")
    return cjk / len(letters) >= 0.5
