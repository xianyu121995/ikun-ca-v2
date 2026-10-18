"""Tweet → Simplified Chinese, strictly after the tweet is already pushed (owner decision 2026-10-18).

Translations are stored as receipts 'tracking.zh.v1:<tweet_id>' = {"text": str, "quote": str|null}
(or {"skip": true} when the tweet is already Chinese). Failures are retried later and never touch the feed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

from . import gemini

KEY = "tracking.zh.v1:"
PROMPT = (
    "把下面的加密货币/Web3 推文翻译成简体中文，给中国用户快速阅读。要求：意思准确、口语自然；"
    "保留 @用户名、$代币符号、链接、数字和专有项目名原样不译；不要添加解释。"
    "只输出 JSON：{\"text\": 推文译文, \"quote\": 被引用推文译文或 null}。\n\n"
)


def translation_for(db, tweet_id):
    row = db.execute("SELECT result FROM receipts WHERE key=?", (KEY + tweet_id,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row[0])
    except ValueError:
        return None
    return None if value.get("skip") else value


def pending(db, limit=5, horizon_s=24 * 3600):
    since_ms = int((time.time() - horizon_s) * 1000)
    rows = db.execute(
        "SELECT t.tweet_id, t.text, t.tweet_kind FROM tweets t JOIN tweet_ledger l ON l.tweet_id=t.tweet_id "
        "WHERE t.tweet_kind IN ('original','quote') AND l.state='visible' AND l.first_received_at_ms>=? "
        "AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.key='tracking.zh.v1:'||t.tweet_id) "
        "GROUP BY t.tweet_id ORDER BY max(l.first_received_at_ms) DESC LIMIT ?",
        (since_ms, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def translate_one(text: str, quote: str | None) -> dict:
    if gemini.mostly_chinese(text) and (not quote or gemini.mostly_chinese(quote)):
        return {"skip": True}
    payload = {"text": text[:4000], "quote": (quote or None) and quote[:4000]}
    value = gemini.generate_json(PROMPT + json.dumps(payload, ensure_ascii=False))
    out_text = value.get("text")
    out_quote = value.get("quote") if quote else None
    if not isinstance(out_text, str) or not out_text.strip():
        raise gemini.AIUnavailable("ai_bad_output")
    return {"text": out_text.strip()[:8000], "quote": out_quote.strip()[:8000] if isinstance(out_quote, str) and out_quote.strip() else None}


def run_pass(store, failures: dict, now=None) -> int:
    """Translate a few recent tweets. Returns how many were stored. Never raises for AI failures."""
    if not gemini.enabled():
        return 0
    now = now or time.time()
    from .feed import quote_for
    with store.connect() as db:
        todo = [r for r in pending(db) if failures.get(r["tweet_id"], 0) <= now]
        for r in todo:
            q = quote_for(db, r["tweet_id"]) if r["tweet_kind"] == "quote" else None
            r["quote"] = q.get("text") if isinstance(q, dict) else None
    stored = 0
    for r in todo:
        try:
            result = translate_one(r["text"] or "", r["quote"])
        except gemini.AIUnavailable as exc:
            failures[r["tweet_id"]] = now + (300 if str(exc) == "ai_rate_limited" else 60)
            logging.getLogger(__name__).warning("tracking_translate_%s", exc)
            if str(exc) in ("ai_not_configured", "ai_key_rejected", "ai_network", "ai_rate_limited", "ai_codex_missing"):
                break
            continue
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with store.connect() as db:
            db.execute("INSERT OR IGNORE INTO receipts(key,fingerprint,result,at) VALUES(?,?,?,?)",
                       (KEY + r["tweet_id"], hashlib.sha256(encoded.encode()).hexdigest(), encoded, time.time()))
        failures.pop(r["tweet_id"], None)
        stored += 1
    if len(failures) > 2000:
        for key in sorted(failures, key=failures.get)[:1000]:
            failures.pop(key, None)
    return stored
