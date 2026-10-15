from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .store import handle


def timestamp(value) -> float | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = value / 1000 if value > 10**12 else float(value)
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                return None
            result = dt.astimezone(UTC).timestamp()
        else:
            return None
        return result if 0 < result <= time.time() + 300 else None
    except (ValueError, TypeError, OverflowError):
        return None


def normalize(content: dict, username: str, require_author=False) -> dict | None:
    if not isinstance(content, dict):
        return None
    # Enforce the event allowlist locally; upstream flags alone are insufficient.
    if any(
        content.get(k)
        for k in (
            "isReply",
            "isQuote",
            "isRetweet",
            "retweetedStatus",
            "retweeted_status",
            "inReplyToStatusId",
            "in_reply_to_status_id",
        )
    ):
        return None
    author = content.get("userScreenName", content.get("screenName"))
    try:
        if (author and handle(author) != username) or (require_author and not author):
            return None
    except (ValueError, AttributeError):
        return None
    tweet_id = str(content.get("id", content.get("id_str", "")))
    created = timestamp(content.get("createdAt", content.get("created_at")))
    text = content.get("text", content.get("full_text", ""))
    if (
        not re.fullmatch(r"[0-9]{1,30}", tweet_id)
        or (created is None and require_author)
        or not isinstance(text, str)
    ):
        return None
    return {"tweet_id": tweet_id, "created_at": created, "text": text[:50000]}


def parse_event(message) -> tuple[str, dict] | None:
    if not isinstance(message, dict) or message.get("method") != "twitter.event":
        return None
    params = message.get("params")
    if not isinstance(params, dict) or params.get("eventType") != "NEW_TWEET":
        return None
    try:
        username = handle(params.get("twAccount", ""))
        content = params.get("content")
        if isinstance(content, str):
            content = json.loads(content)
        tweet = normalize(content, username)
        return (username, tweet) if tweet else None
    except (ValueError, TypeError, AttributeError):
        return None
