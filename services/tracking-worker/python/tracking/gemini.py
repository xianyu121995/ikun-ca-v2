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
    key = data.get("api_key")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]{20,300}", key):
        return None
    model = data.get("model") if isinstance(data.get("model"), str) and re.fullmatch(r"[A-Za-z0-9._\-]{1,80}", data.get("model")) else "gemini-flash-latest"
    proxy = data.get("proxy") if isinstance(data.get("proxy"), str) and re.fullmatch(r"(https?|socks5h?)://[A-Za-z0-9.\-]+:\d{1,5}", data.get("proxy")) else None
    return {"api_key": key, "model": model, "proxy": proxy}


def enabled():
    return settings() is not None


def generate_json(prompt: str, *, timeout: float = 25.0) -> dict:
    cfg = settings()
    if cfg is None:
        raise AIUnavailable("ai_not_configured")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    headers = {"x-goog-api-key": cfg["api_key"], "content-type": "application/json"}
    # AI Studio now issues "AQ." auth keys as well as legacy "AIza" keys; both go in x-goog-api-key.
    models = [cfg["model"]] + [m for m in FALLBACK_MODELS if m != cfg["model"]]
    if _WORKING["model"] in models:
        models.remove(_WORKING["model"]); models.insert(0, _WORKING["model"])
    try:
        with httpx.Client(proxy=cfg["proxy"], timeout=timeout, trust_env=cfg["proxy"] is None) as client:
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
