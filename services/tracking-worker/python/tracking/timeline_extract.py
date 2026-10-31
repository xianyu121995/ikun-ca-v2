"""Tweet → homepage timeline entry. Reads tweets already stored by tracking; never calls 6551.

Cross-service contract (phase2-v1.0.0):
- Writer is tracking.db receipts only (no schema bump, no projects.db, no ATTACH).
- Keys: tracking.timeline.analyze.v1:<tweet_id> (one analysis per tweet),
  tracking.timeline.entry.v1:<entry_id>, tracking.timeline.slot.v1:<project_id>:<type>.
- The website BFF reads GET /internal/v1/timeline-events and renders those rows on the
  existing homepage timeline. PATCH/DELETE edit or tombstone an entry. A tombstone for
  (project, type) is never recreated by a later pass.
- Human milestones in projects.db are not written or overwritten.
- Flag: ai.json "timeline_extract": true. Absent or any other value leaves the pass off.
  AI failures are not recorded, so they retry; a finished analysis is recorded once.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import gemini
from .protocol import DomainError

ANALYZE = "tracking.timeline.analyze.v1:"
ENTRY = "tracking.timeline.entry.v1:"
SLOT = "tracking.timeline.slot.v1:"
TYPES = ("tge", "mint", "airdrop", "listing", "whitelist", "launch", "mainnet", "snapshot", "other")
HIGH_CONFIDENCE = 0.8
NEAR_S = 6 * 3600
MAX_OFFSET_S = 366 * 86400
SHANGHAI = timezone(timedelta(hours=8))
NS = uuid.UUID("6f0e2a1c-9b44-5d17-8c3a-1e7b9a0d4f21")
ENTRY_ID = re.compile(r"^tle_[0-9a-f]{32}$")
PROJECT_ID = re.compile(r"^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
TWEET_ID = re.compile(r"^[0-9]{1,40}$")
LOG = logging.getLogger(__name__)
ZONE_ALIASES = {
    "UTC": "UTC", "Z": "UTC", "GMT": "UTC", "UTC+0": "UTC", "UTC+00:00": "UTC",
    "ASIA/SHANGHAI": "Asia/Shanghai", "SHANGHAI": "Asia/Shanghai", "BEIJING": "Asia/Shanghai",
    "ASIA/BEIJING": "Asia/Shanghai", "CST": "Asia/Shanghai", "CHINA": "Asia/Shanghai",
    "UTC+8": "Asia/Shanghai", "UTC+08": "Asia/Shanghai", "UTC+08:00": "Asia/Shanghai",
    "GMT+8": "Asia/Shanghai", "GMT+08:00": "Asia/Shanghai", "+08:00": "Asia/Shanghai",
    "北京时间": "Asia/Shanghai", "北京": "Asia/Shanghai",
    "ASIA/HONG_KONG": "Asia/Shanghai", "ASIA/SINGAPORE": "Asia/Shanghai", "ASIA/TAIPEI": "Asia/Shanghai",
}
PROMPT = (
    "你是加密项目研究助手。阅读下面这条已抓取的推文（含被引用推文），判断它是否公布了一个"
    "有具体日期或时刻的事件（上线、TGE、发币、开盘、mint、空投、上所、白名单、主网、快照）。\n"
    "规则：soon、即将、Q4、本月、稍后这类没有具体日期的说法 concrete=false，kind=vague，不要猜日期。"
    "相对时间用 schedule，不要自己换算：'in 2 hours' → {\"kind\":\"relative\",\"seconds\":7200}；"
    "'tomorrow 20:00 UTC' → {\"kind\":\"wall\",\"day_offset\":1,\"hour\":20,\"minute\":0,\"timezone\":\"UTC\"}；"
    "绝对时间必须带时区，例如 {\"kind\":\"absolute\",\"iso\":\"2026-11-02T20:00:00Z\"}；"
    "只有日期没有钟点 → {\"kind\":\"date\",\"date\":\"2026-11-02\",\"timezone\":\"Asia/Shanghai\",\"hour\":null}。\n"
    "只写钟点、没写日期（如 '12:00'、'12：00'、'晚8点'）也算具体时刻：用 wall，没写时区默认 Asia/Shanghai；"
    "参照 created_at_local（发推的北京时间），该钟点今天还没到 day_offset=0，已过则 day_offset=1。"
    "例：23:52 发 '官方池12：00建立' → {\"kind\":\"wall\",\"day_offset\":1,\"hour\":12,\"minute\":0,\"timezone\":\"Asia/Shanghai\"}。"
    "全角冒号 '：' 与半角 ':' 等价。\n"
    "建池、开池、加池子、官方池建立、开盘、开放交易都算 launch 事件，announces=true。\n"
    "event_type 只能是 tge,mint,airdrop,listing,whitelist,launch,mainnet,snapshot,other 之一。"
    "title 用不超过 40 字的简体中文。confidence 是 0 到 1 的小数，明确写出时间才 ≥0.8；明确写出钟点（即使没写日期）也应 ≥0.8。\n"
    "只输出一个 JSON：{\"announces\":true|false,\"event_type\":\"tge\",\"title\":\"\",\"confidence\":0.0,"
    "\"concrete\":true|false,\"schedule\":{\"kind\":\"vague\"}}。\n\n"
)


def extract_enabled() -> bool:
    path = Path(os.environ.get("IKUN_AI_CONFIG") or gemini.DEFAULT_PATH)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("timeline_extract") is True


def _number(value, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if integer and (isinstance(value, float) and not value.is_integer()):
        return None
    return int(value) if integer else float(value)


def _zone(name):
    if isinstance(name, str):
        name = ZONE_ALIASES.get(name.strip().upper(), ZONE_ALIASES.get(name.strip(), name.strip()))
    if name in ("UTC", "Z", "GMT"):
        return timezone.utc
    if name == "Asia/Shanghai":
        return SHANGHAI
    matched = re.fullmatch(r"([+-])(\d{2}):(\d{2})", name or "")
    if not matched:
        return None
    sign = 1 if matched.group(1) == "+" else -1
    hours, minutes = int(matched.group(2)), int(matched.group(3))
    if hours > 14 or minutes > 59 or (hours == 14 and minutes):
        return None
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def _parse_absolute(iso) -> datetime | None:
    if not isinstance(iso, str) or len(iso) > 40:
        return None
    text = iso[:-1] + "+00:00" if iso.endswith("Z") else iso
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _aware(parsed)


def _at_clock(day: datetime, hour: int, minute: int, zone) -> datetime:
    local = day.astimezone(zone)
    stamped = datetime(local.year, local.month, local.day, hour, minute, tzinfo=zone)
    return stamped.astimezone(timezone.utc)


def _schedule(schedule, created_at: float | None) -> tuple[datetime, str | None] | None:
    """Return (utc instant, display hour or None when the source had no clock)."""
    if not isinstance(schedule, dict):
        return None
    kind = schedule.get("kind")
    if kind == "vague":
        return None
    if kind == "absolute":
        when = _parse_absolute(schedule.get("iso"))
        return None if when is None else (when, f"{when.astimezone(SHANGHAI).hour:02d}")
    if kind == "date":
        zone = _zone(schedule.get("timezone"))
        date = schedule.get("date")
        if zone is None or not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return None
        try:
            day = datetime.fromisoformat(date)
        except ValueError:
            return None
        hour = schedule.get("hour")
        if hour is None:
            return _at_clock(day.replace(tzinfo=zone), 12, 0, zone), None
        clock = _number(hour, integer=True)
        minute = _number(schedule.get("minute", 0), integer=True)
        if clock is None or minute is None or not 0 <= clock <= 23 or not 0 <= minute <= 59:
            return None
        return _at_clock(day.replace(tzinfo=zone), clock, minute, zone), None  # hour filled below
    created = None if created_at is None else datetime.fromtimestamp(created_at, timezone.utc)
    if kind == "relative":
        seconds = _number(schedule.get("seconds"), integer=True)
        if created is None or seconds is None or not 0 < seconds <= MAX_OFFSET_S:
            return None
        when = created + timedelta(seconds=seconds)
        return when, f"{when.astimezone(SHANGHAI).hour:02d}"
    if kind in ("wall", "time", "clock"):
        tz_name = schedule.get("timezone")
        # Clock-only tweets ("12：00") usually omit the zone; default to Beijing time.
        zone = SHANGHAI if tz_name in (None, "") else _zone(tz_name)
        clock = _number(schedule.get("hour"), integer=True)
        minute = _number(schedule.get("minute") if schedule.get("minute") is not None else 0, integer=True)
        if zone is None or created is None or clock is None or minute is None:
            return None
        if not 0 <= clock <= 23 or not 0 <= minute <= 59:
            return None
        raw_offset = schedule.get("day_offset")
        if raw_offset is None:
            # Next occurrence of that clock after the tweet was posted.
            today = _at_clock(created, clock, minute, zone)
            offset = 0 if today > created else 1
        else:
            offset = _number(raw_offset, integer=True)
        if offset is None:
            return None
        if not 0 <= offset <= 366 or not 0 <= clock <= 23 or not 0 <= minute <= 59:
            return None
        day = created.astimezone(zone) + timedelta(days=offset)
        return _at_clock(day, clock, minute, zone), f"{_at_clock(day, clock, minute, zone).astimezone(SHANGHAI).hour:02d}"
    return None


def interpret(raw: dict, created_at: float | None) -> dict | None:
    """Normalize one model object. None means it must not be added to the timeline."""
    return explain(raw, created_at)[0]


def explain(raw: dict, created_at: float | None) -> tuple[dict | None, str | None]:
    """Like interpret, plus why a result was dropped (None reason when kept)."""
    if not isinstance(raw, dict):
        return None, "not_object"
    if raw.get("announces") is not True:
        return None, "announces_false"
    if raw.get("concrete") is not True:
        return None, "concrete_false"
    confidence = _number(raw.get("confidence"))
    if confidence is None or not HIGH_CONFIDENCE <= confidence <= 1:
        return None, "low_confidence"
    event_type = raw.get("event_type")
    title = raw.get("title")
    if event_type not in TYPES:
        return None, "bad_event_type"
    if not isinstance(title, str) or not title.strip():
        return None, "empty_title"
    schedule = raw.get("schedule")
    resolved = _schedule(schedule, created_at)
    if resolved is None:
        kind = schedule.get("kind") if isinstance(schedule, dict) else None
        return None, "vague_schedule" if kind == "vague" else "bad_schedule"
    when, hour = resolved
    if schedule.get("kind") == "date" and schedule.get("hour") is not None:
        clock = _number(schedule.get("hour"), integer=True)
        if clock is None:
            return None, "bad_schedule"
        # Display the source clock converted to Asia/Shanghai, not the noon placeholder.
        hour = f"{when.astimezone(SHANGHAI).hour:02d}"
    local = when.astimezone(SHANGHAI)
    status = "confirmed" if confidence >= 0.9 and hour is not None else "estimated"
    return {
        "event_type": event_type,
        "title": title.strip()[:60],
        "confidence": confidence,
        "starts_at": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": local.date().isoformat(),
        "hour": hour,
        "status": status,
    }, None


def entry_id_for(project_id: str, event_type: str) -> str:
    return "tle_" + uuid.uuid5(NS, project_id + "\n" + event_type).hex


def source_url(handle: str, tweet_id: str) -> str | None:
    if HANDLE.fullmatch(handle or "") and TWEET_ID.fullmatch(tweet_id or ""):
        return f"https://x.com/{handle}/status/{tweet_id}"
    return None


def _loads(row):
    if not row:
        return None
    try:
        value = json.loads(row[0])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _get(db, key):
    return _loads(db.execute("SELECT result FROM receipts WHERE key=?", (key,)).fetchone())


def _put(db, key, obj, at):
    encoded = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    db.execute(
        "INSERT INTO receipts(key,fingerprint,result,at) VALUES(?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET fingerprint=excluded.fingerprint,result=excluded.result,at=excluded.at",
        (key, hashlib.sha256(encoded.encode()).hexdigest(), encoded, at),
    )


def _starts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def apply_event(db, tweet: dict, event: dict, now: float) -> str:
    """Insert or update the single (project, type) entry. Returns the action name."""
    project_id = tweet.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        return "ignored"
    event_type = event["event_type"]
    slot_key = SLOT + project_id + ":" + event_type
    slot = _get(db, slot_key)
    eid = entry_id_for(project_id, event_type)
    if slot and slot.get("state") == "tombstone":
        return "tombstone"
    url = source_url(tweet.get("handle") or "", tweet.get("tweet_id") or "")
    current = _get(db, ENTRY + eid) if slot and slot.get("state") == "active" else None
    if current and current.get("state") == "active":
        if current.get("user_locked") is True:
            return "locked"
        delta = abs((_starts(event["starts_at"]) - _starts(current["starts_at"])).total_seconds())
        current["source_tweet_id"] = tweet["tweet_id"]
        current["source_url"] = url
        if delta > NEAR_S or event["confidence"] > float(current.get("confidence") or 0):
            current.update(
                title=event["title"],
                starts_at=event["starts_at"],
                date=event["date"],
                hour=event["hour"],
                status=event["status"],
                confidence=event["confidence"],
            )
            action = "rescheduled" if delta > NEAR_S else "updated"
        else:
            action = "updated"
        _put(db, ENTRY + eid, current, now)
        _put(db, slot_key, {"state": "active", "entry_id": eid}, now)
        return action
    _put(
        db,
        ENTRY + eid,
        {
            "entry_id": eid,
            "project_id": project_id,
            "project_name": str(tweet.get("project_name") or "")[:120],
            "event_type": event_type,
            "title": event["title"],
            "starts_at": event["starts_at"],
            "date": event["date"],
            "hour": event["hour"],
            "status": event["status"],
            "confidence": event["confidence"],
            "source_tweet_id": tweet.get("tweet_id"),
            "source_url": url,
            "state": "active",
            "user_locked": False,
        },
        now,
    )
    _put(db, slot_key, {"state": "active", "entry_id": eid}, now)
    return "created"


def pending(db, limit=8, horizon_s=24 * 3600):
    since_ms = int((time.time() - horizon_s) * 1000)
    rows = db.execute(
        "SELECT t.tweet_id, t.text, t.tweet_kind, t.created_at, t.project_id, t.handle, p.name AS project_name "
        "FROM tweets t JOIN tweet_ledger l ON l.tweet_id=t.tweet_id "
        "JOIN projects p ON p.project_id=t.project_id "
        "WHERE t.tweet_kind IN ('original','quote') AND l.state='visible' AND l.first_received_at_ms>=? "
        "AND NOT EXISTS (SELECT 1 FROM receipts r WHERE r.key=?||t.tweet_id) "
        "GROUP BY t.tweet_id ORDER BY max(l.first_received_at_ms) DESC LIMIT ?",
        (since_ms, ANALYZE, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _model_summary(raw) -> dict | None:
    """A small, size-capped copy of the model answer kept for debugging dropped tweets."""
    if not isinstance(raw, dict):
        return None
    keep = {}
    for key in ("announces", "concrete", "event_type", "confidence"):
        value = raw.get(key)
        if value is None or isinstance(value, (bool, int, float)) or (isinstance(value, str) and len(value) <= 40):
            keep[key] = value
    title = raw.get("title")
    if isinstance(title, str):
        keep["title"] = title[:60]
    schedule = raw.get("schedule")
    if isinstance(schedule, dict):
        encoded = json.dumps(schedule, ensure_ascii=False)
        keep["schedule"] = schedule if len(encoded) <= 300 else {"kind": str(schedule.get("kind"))[:20]}
    return keep


def run_pass(store, failures: dict, now=None) -> int:
    """Analyze a few recent tweets. Returns how many analyses were stored. Never raises for AI failures."""
    if not extract_enabled() or not gemini.enabled():
        return 0
    now = now or time.time()
    from .feed import quote_for

    with store.connect() as db:
        todo = [r for r in pending(db) if failures.get(r["tweet_id"], 0) <= now][:1]
        for row in todo:
            quoted = quote_for(db, row["tweet_id"]) if row["tweet_kind"] == "quote" else None
            row["quote"] = quoted.get("text") if isinstance(quoted, dict) else None
    stored = 0
    for row in todo:
        text = row.get("text") or ""
        quote = row.get("quote") or ""
        if not text.strip() and not quote.strip():
            result, action, reason, model = None, "none", "empty_text", None
        else:
            created_at = row.get("created_at")
            local = None
            if isinstance(created_at, (int, float)) and not isinstance(created_at, bool):
                local = datetime.fromtimestamp(created_at, SHANGHAI).strftime("%Y-%m-%d %H:%M (Asia/Shanghai)")
            payload = {
                "text": text[:4000],
                "quote": quote[:2000] or None,
                "created_at": created_at,
                "created_at_local": local,
            }
            try:
                raw = gemini.generate_json(PROMPT + json.dumps(payload, ensure_ascii=False))
            except gemini.AIUnavailable as exc:
                failures[row["tweet_id"]] = now + (300 if str(exc) == "ai_rate_limited" else 60)
                if str(exc) in ("ai_not_configured", "ai_key_rejected", "ai_codex_missing"):
                    break
                continue
            result, reason = explain(raw, row.get("created_at"))
            action = None
            model = _model_summary(raw)
            if reason:
                LOG.info("tracking_timeline_dropped tweet_id=%s reason=%s", row["tweet_id"], reason)
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if _get(db, ANALYZE + row["tweet_id"]):
                    db.execute("COMMIT")
                    continue
                if result is not None and action is None:
                    action = apply_event(db, row, result, now)
                recorded = {"applied": action or "none", "event": result}
                if result is None:
                    recorded["reason"] = reason
                    if model is not None:
                        recorded["model"] = model
                _put(db, ANALYZE + row["tweet_id"], recorded, now)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        failures.pop(row["tweet_id"], None)
        stored += 1
    if len(failures) > 2000:
        for key in sorted(failures, key=failures.get)[:1000]:
            failures.pop(key, None)
    return stored


def _public(entry: dict) -> dict | None:
    url = entry.get("source_url")
    if url is not None and not (isinstance(url, str) and re.fullmatch(r"https://x\.com/[A-Za-z0-9_]{1,15}/status/[0-9]{1,40}", url)):
        return None
    hour = entry.get("hour")
    if hour is not None and not (isinstance(hour, str) and re.fullmatch(r"(?:[01]\d|2[0-3])", hour)):
        return None
    if entry.get("event_type") not in TYPES or entry.get("status") not in ("confirmed", "estimated"):
        return None
    if not ENTRY_ID.fullmatch(entry.get("entry_id") or "") or not PROJECT_ID.fullmatch(entry.get("project_id") or ""):
        return None
    if not isinstance(entry.get("title"), str) or not entry["title"].strip():
        return None
    if not isinstance(entry.get("date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["date"]):
        return None
    if not TWEET_ID.fullmatch(str(entry.get("source_tweet_id") or "")):
        return None
    try:
        _starts(entry.get("starts_at"))
    except (TypeError, ValueError):
        return None
    confidence = entry.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    return {
        "entry_id": entry["entry_id"],
        "project_id": entry["project_id"],
        "project_name": str(entry.get("project_name") or "")[:120],
        "event_type": entry["event_type"],
        "title": entry["title"][:60],
        "starts_at": entry["starts_at"],
        "date": entry["date"],
        "hour": hour,
        "status": entry["status"],
        "confidence": float(confidence),
        "source_tweet_id": str(entry["source_tweet_id"]),
        "source_url": url,
    }


def list_public(db) -> list[dict]:
    rows = db.execute("SELECT result FROM receipts WHERE key LIKE ?", (ENTRY + "%",)).fetchall()
    items = []
    for row in rows:
        value = _loads(row)
        if not value or value.get("state") != "active":
            continue
        public = _public(value)
        if public:
            items.append(public)
    items.sort(key=lambda item: (item["starts_at"], item["entry_id"]))
    return items[:100]


def _require_entry(entry_id: str) -> str:
    if not ENTRY_ID.fullmatch(entry_id or ""):
        raise DomainError(422, "VALIDATION_ERROR", "时间线条目 ID 不正确")
    return entry_id


def _patch_fields(patch: dict) -> dict:
    if not isinstance(patch, dict) or set(patch) - {"date", "hour", "title", "status"}:
        raise DomainError(422, "VALIDATION_ERROR", "时间线条目字段不正确")
    date = patch.get("date")
    hour = patch.get("hour")
    title = patch.get("title")
    status = patch.get("status")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise DomainError(422, "VALIDATION_ERROR", "日期不正确")
    try:
        datetime.fromisoformat(date)
    except ValueError:
        raise DomainError(422, "VALIDATION_ERROR", "日期不正确") from None
    if hour is not None and (not isinstance(hour, str) or not re.fullmatch(r"(?:[01]\d|2[0-3])", hour)):
        raise DomainError(422, "VALIDATION_ERROR", "小时不正确")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 60:
        raise DomainError(422, "VALIDATION_ERROR", "事件说明不正确")
    if status not in ("confirmed", "estimated"):
        raise DomainError(422, "VALIDATION_ERROR", "状态不正确")
    clock = int(hour) if hour else 12
    starts = datetime(int(date[0:4]), int(date[5:7]), int(date[8:10]), clock, tzinfo=SHANGHAI).astimezone(timezone.utc)
    return {
        "date": date,
        "hour": hour,
        "title": title.strip(),
        "status": status,
        "starts_at": starts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _receipt(db, actor_id, route, key, body_hash):
    return db.execute(
        "SELECT response,body_hash FROM public_receipts WHERE actor_id=? AND route=? AND key=?",
        (actor_id, route, key),
    ).fetchone()


def edit_entry(store, entry_id: str, patch: dict, actor_id: str, idempotency_key: str) -> dict:
    entry_id = _require_entry(entry_id)
    fields = _patch_fields(patch)
    route = "PATCH /timeline-events/" + entry_id
    hashed = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            previous = _receipt(db, actor_id, route, idempotency_key, hashed)
            if previous:
                if previous["body_hash"] != hashed:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键对应了不同操作")
                db.execute("COMMIT")
                return json.loads(previous["response"])
            current = _get(db, ENTRY + entry_id)
            if not current or current.get("state") != "active":
                raise DomainError(404, "NOT_FOUND", "时间线条目不存在")
            current.update(fields)
            current["user_locked"] = True
            _put(db, ENTRY + entry_id, current, time.time())
            public = _public(current)
            if public is None:
                raise DomainError(422, "VALIDATION_ERROR", "时间线条目无法保存")
            db.execute(
                "INSERT INTO public_receipts(actor_id,route,key,body_hash,response,created_at) VALUES(?,?,?,?,?,?)",
                (actor_id, route, idempotency_key, hashed, json.dumps(public, ensure_ascii=False, separators=(",", ":")), time.time()),
            )
            db.execute("COMMIT")
            return public
        except Exception:
            db.execute("ROLLBACK")
            raise


def delete_entry(store, entry_id: str, actor_id: str, idempotency_key: str) -> dict:
    entry_id = _require_entry(entry_id)
    route = "DELETE /timeline-events/" + entry_id
    hashed = hashlib.sha256(b"delete").hexdigest()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            previous = _receipt(db, actor_id, route, idempotency_key, hashed)
            if previous:
                if previous["body_hash"] != hashed:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键对应了不同操作")
                db.execute("COMMIT")
                return json.loads(previous["response"])
            current = _get(db, ENTRY + entry_id)
            if not current or current.get("state") != "active":
                raise DomainError(404, "NOT_FOUND", "时间线条目不存在")
            current["state"] = "deleted"
            now = time.time()
            _put(db, ENTRY + entry_id, current, now)
            _put(
                db,
                SLOT + current["project_id"] + ":" + current["event_type"],
                {"state": "tombstone", "entry_id": entry_id},
                now,
            )
            body = {"entry_id": entry_id, "deleted": True}
            db.execute(
                "INSERT INTO public_receipts(actor_id,route,key,body_hash,response,created_at) VALUES(?,?,?,?,?,?)",
                (actor_id, route, idempotency_key, hashed, json.dumps(body, separators=(",", ":")), now),
            )
            db.execute("COMMIT")
            return body
        except Exception:
            db.execute("ROLLBACK")
            raise
