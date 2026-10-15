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


def normalize(content: dict, username: str, require_author=False, *, event_type="NEW_TWEET") -> dict | None:
    """Map documented 6551 author/boolean fields; never infer type from prose."""
    if not isinstance(content, dict):
        return None
    author = content.get("userScreenName", content.get("screenName"))
    author_id = content.get("userIdStr")
    try:
        if not isinstance(author, str) or handle(author) != username:
            return None
    except (ValueError, AttributeError):
        return None
    if author_id is not None and (
        not isinstance(author_id, str) or not re.fullmatch(r"[0-9]{1,40}", author_id)
    ):
        return None
    reply, quote, repost = content.get("isReply"), content.get("isQuote"), content.get("isRetweet")
    flags_valid = all(value is None or type(value) is bool for value in (reply, quote, repost))
    if not flags_valid:
        kind = "unknown"
    elif repost is True or content.get("retweetedStatus") or content.get("retweeted_status"):
        kind = "repost"
    elif reply is True or content.get("inReplyToStatusId") or content.get("in_reply_to_status_id"):
        kind = "reply"
    elif event_type == "NEW_TWEET_QUOTE":
        kind = "unknown" if quote is False else "quote"
    elif quote is True and reply is False:
        kind = "quote"
    elif reply is False and quote is False and event_type in ("NEW_TWEET", "REST_USER_TWEETS_NO_RETWEETS"):
        kind = "original"
    else:
        kind = "unknown"
    tweet_id = str(content.get("id", content.get("id_str", "")))
    created = timestamp(content.get("createdAt", content.get("created_at")))
    text = content.get("text", content.get("full_text", ""))
    if not re.fullmatch(r"[0-9]{1,40}", tweet_id) or not isinstance(text, str):
        return None
    if require_author and created is None:
        return None
    return {
        "tweet_id": tweet_id,
        "created_at": created,
        "text": text[:20000],
        "tweet_kind": kind,
        "type_evidence_version": "6551-structured-v1",
        "author_verified": True,
        "author_handle": username,
        "author_id": author_id,
    }


def parse_event(message) -> tuple[str, dict] | None:
    if not isinstance(message, dict) or message.get("method") != "twitter.event":
        return None
    params = message.get("params")
    if not isinstance(params, dict) or params.get("eventType") not in ("NEW_TWEET", "NEW_TWEET_QUOTE"):
        return None
    try:
        username = handle(params.get("twAccount", ""))
        content = params.get("content")
        if isinstance(content, str):
            content = json.loads(content)
        tweet = normalize(content, username, event_type=params["eventType"])
        return (username, tweet) if tweet else None
    except (ValueError, TypeError, AttributeError):
        return None
