"""Official X API v2 filtered stream. Rules are account watches; posts map into the tweet model.

Operators are the documented core set: standalone `from:` plus negated `is:retweet` and `is:reply`.
Quote posts stay in (they are not retweets). Pay-per-use has no recovery backfill, so this module
never sends `backfill_minutes` and never reads user timelines.
"""
from __future__ import annotations

import re

from .events import normalize, note
from .store import handle

RULES_PATH = "/2/tweets/search/stream/rules"
STREAM_PATH = "/2/tweets/search/stream"
TAG_PREFIX = "ikun-ca-v2:tracking:"
REMARK = "ikun-ca-v2:tracking"
OWNED_GROUP = "ikun-ca-v2-project-tracking"
SILENCE_SECONDS = 25.0
STREAM_QUERY = {
    "tweet.fields": "created_at,author_id,conversation_id,referenced_tweets,note_tweet,in_reply_to_user_id",
    "expansions": "author_id,referenced_tweets.id,referenced_tweets.id.author_id",
    "user.fields": "username,name",
}
OTHER_FLAGS = (
    "newFlwBol",
    "newUnFlwBol",
    "newTweetReplyBol",
    "newTweetQuoteBol",
    "newRetweetBol",
    "updateNameBol",
    "updateDescBol",
    "updateAvatarBol",
    "updateBannerBol",
    "newCaBol",
    "tweetToppingBol",
)
_EXTRA_TRUE = tuple(flag for flag in OTHER_FLAGS if flag != "newTweetQuoteBol")
_TAG_FLAGS = set(_EXTRA_TRUE) | {"paused", "suspended", "blacked", "notweet"}
_FROM = re.compile(r"(?:^|\s)from:([A-Za-z0-9_]{1,15})(?=\s|$)")


class RuleError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def standard_value(account: str) -> str:
    return f"from:{handle(account)} -is:retweet -is:reply"


def rule_for_watch(row: dict, owned_group: str = OWNED_GROUP) -> dict:
    """Test/helper encoding of a watch row into one filtered-stream rule."""
    account = handle(row.get("twAccount", row.get("username", "")))
    extra = []
    if row.get("newTweetBol") is not True:
        extra.append("notweet")
    for name in _EXTRA_TRUE:
        if row.get(name) is True:
            extra.append(name)
    for name, token in (("isPaused", "paused"), ("isSuspended", "suspended"), ("isBlacked", "blacked")):
        if row.get(name) is True:
            extra.append(token)
    owned = row.get("remark") == REMARK or row.get("groupName") == owned_group
    prefix = f"{TAG_PREFIX}{account}" if owned else f"external:{account}"
    tag = prefix if not extra else prefix + "+" + "+".join(extra)
    pure = "notweet" not in extra and "newTweetReplyBol" not in extra and "newRetweetBol" not in extra
    rule = {"value": standard_value(account) if pure else f"from:{account}", "tag": tag}
    if row.get("id") is not None:
        rule["id"] = str(row["id"])
    return rule


def _tag_flags(tag: str, account: str) -> tuple[bool, list[str]]:
    if tag.startswith(TAG_PREFIX):
        name, _, extra = tag[len(TAG_PREFIX) :].partition("+")
        if name != account:
            raise RuleError("invalid_watch_snapshot")
        return True, [part for part in extra.split("+") if part] if extra else []
    if tag.startswith("external:"):
        name, _, extra = tag[len("external:") :].partition("+")
        if name != account:
            raise RuleError("invalid_watch_snapshot")
        return False, [part for part in extra.split("+") if part] if extra else []
    return False, []


def watch_from_rule(rule: dict, watch_group: str) -> dict | None:
    """Map one rules-list entry into the watch record the worker already reconciles."""
    value = rule.get("value")
    if not isinstance(value, str):
        raise RuleError("invalid_watch_snapshot")
    found = _FROM.findall(value)
    if len(found) > 1:
        raise RuleError("invalid_watch_snapshot")
    if not found:
        return None
    account = handle(found[0])
    rule_id = rule.get("id")
    if type(rule_id) not in (str, int) or isinstance(rule_id, bool) or not re.fullmatch(r"[0-9]{1,40}", str(rule_id)):
        raise RuleError("invalid_watch_snapshot")
    owned, flags = _tag_flags(rule.get("tag") if isinstance(rule.get("tag"), str) else "", account)
    if any(flag not in _TAG_FLAGS for flag in flags):
        raise RuleError("invalid_watch_snapshot")
    exact = value.lower() == standard_value(account)
    tweet_on = exact and "notweet" not in flags and "newTweetReplyBol" not in flags and "newRetweetBol" not in flags
    watch = {
        "id": str(rule_id),
        "twAccount": account,
        "username": account,
        "groupName": watch_group if owned else "external",
        "remark": REMARK if owned else "external",
        "newTweetBol": tweet_on,
        "newTweetQuoteBol": True,
        "isPaused": "paused" in flags,
        "isSuspended": "suspended" in flags,
        "isBlacked": "blacked" in flags,
    }
    for name in _EXTRA_TRUE:
        watch[name] = name in flags
    return watch


def _full_text(post: dict) -> str:
    note_tweet = post.get("note_tweet")
    if isinstance(note_tweet, dict) and isinstance(note_tweet.get("text"), str) and note_tweet["text"]:
        return note_tweet["text"]
    text = post.get("text")
    return text if isinstance(text, str) else ""


def parse_stream_post(payload, on_drop=None):
    """Map one filtered-stream object into (handle, tweet) for the existing ingest path."""
    if not isinstance(payload, dict):
        note(on_drop, "invalid_content_shape")
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        note(on_drop, "invalid_content_shape")
        return None
    includes = payload.get("includes") if isinstance(payload.get("includes"), dict) else {}
    users = {
        str(user.get("id")): user
        for user in includes.get("users") or []
        if isinstance(user, dict) and user.get("id") is not None
    }
    tweets = {
        str(item.get("id")): item
        for item in includes.get("tweets") or []
        if isinstance(item, dict) and item.get("id") is not None
    }
    author = users.get(str(data.get("author_id"))) if data.get("author_id") is not None else None
    try:
        account = handle((author or {}).get("username"))
    except (ValueError, AttributeError, TypeError):
        note(on_drop, "author_handle_missing_or_mismatch")
        return None
    refs = data.get("referenced_tweets") if isinstance(data.get("referenced_tweets"), list) else []
    types = set()
    quoted_id = None
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        kind = ref.get("type")
        if kind in ("retweeted", "replied_to", "quoted"):
            types.add(kind)
        if kind == "quoted" and quoted_id is None:
            quoted_id = str(ref.get("id") or "")
    if "retweeted" in types or "replied_to" in types or data.get("in_reply_to_user_id"):
        note(on_drop, "not_tracking_tweet_event")
        return None
    content = {
        "id": str(data.get("id") or ""),
        "text": _full_text(data),
        "created_at": data.get("created_at"),
        "userScreenName": account,
        "userIdStr": None if data.get("author_id") is None else str(data.get("author_id")),
        "isReply": False,
        "isQuote": "quoted" in types,
        "isRetweet": False,
    }
    quoted = tweets.get(quoted_id) if quoted_id else None
    if isinstance(quoted, dict):
        quser = users.get(str(quoted.get("author_id"))) if quoted.get("author_id") is not None else {}
        content["quotedStatus"] = {
            "id": quoted_id,
            "text": _full_text(quoted),
            "userScreenName": (quser or {}).get("username"),
            "userName": (quser or {}).get("name"),
        }
    event_type = "NEW_TWEET_QUOTE" if content["isQuote"] else "NEW_TWEET"
    tweet = normalize(
        content,
        account,
        event_type=event_type,
        on_drop=on_drop,
        evidence_version="x-stream-structured-v1",
    )
    if not tweet or tweet["tweet_kind"] not in ("original", "quote"):
        note(on_drop, "not_tracking_tweet_event")
        return None
    return account, tweet


def audit_message(message):
    """Allowlisted audit fields only. Never copy post text into the log envelope."""
    if not isinstance(message, dict) or message.get("method") or not isinstance(message.get("data"), dict):
        return message
    data = message["data"]
    includes = message.get("includes") if isinstance(message.get("includes"), dict) else {}
    users = {str(user.get("id")): user for user in includes.get("users") or [] if isinstance(user, dict)}
    author = users.get(str(data.get("author_id"))) if data.get("author_id") is not None else {}
    username = author.get("username") if isinstance(author, dict) and isinstance(author.get("username"), str) else ""
    refs = data.get("referenced_tweets") if isinstance(data.get("referenced_tweets"), list) else []
    types = {ref.get("type") for ref in refs if isinstance(ref, dict)}
    if "retweeted" in types:
        kind = "NEW_RETWEET"
    elif "replied_to" in types or data.get("in_reply_to_user_id"):
        kind = "NEW_TWEET_REPLY"
    elif "quoted" in types:
        kind = "NEW_TWEET_QUOTE"
    else:
        kind = "NEW_TWEET"
    return {"params": {"eventType": kind, "twAccount": username, "content": {"id": data.get("id")}}}
