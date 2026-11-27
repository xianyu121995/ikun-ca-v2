"""Official timestamps, always displayed in Asia/Shanghai."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_zone_label(label: str | None):
    """Map an official timezone label. Unknown labels are not assumed."""
    text = re.sub(r"\s+", "", (label or "")).upper()
    if text in {"UTC", "UTC+0", "UTC+00", "UTC+00:00", "UTC±0"}:
        return UTC
    if text in {"UTC+8", "UTC+08", "UTC+08:00", "UTC+8:00"}:
        return BEIJING
    if "东八区" in (label or "") or text in {"ASIA/SHANGHAI", "CST"}:
        return BEIJING
    if text in {"UTC+7", "UTC+07", "ASIA/BANGKOK"} or "曼谷" in (label or ""):
        return BANGKOK
    return None


def parse_naive(value: str | None, zone) -> datetime | None:
    if not value or zone is None:
        return None
    text = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=zone)
    return None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def as_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def beijing_clock(value: datetime) -> str:
    return value.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")


def format_instant_range(start: datetime | None, end: datetime | None, source_note: str = "") -> str:
    if start and end:
        text = f"{beijing_clock(start)} 至 {beijing_clock(end)} 北京时间（UTC+8）"
    elif start:
        text = f"{beijing_clock(start)} 起 北京时间（UTC+8）"
    elif end:
        text = f"截至 {beijing_clock(end)} 北京时间（UTC+8）"
    else:
        text = ""
    if source_note:
        text = f"{text}；{source_note}" if text else source_note
    return text


def calendar_span(year: int, month: int, day_start: int, day_end: int, month_end: int | None, zone) -> tuple[datetime, datetime]:
    """Inclusive calendar dates in `zone`, as [start, end) instants."""
    end_month = month_end or month
    start = datetime(year, month, day_start, tzinfo=zone)
    end_day = datetime(year, end_month, day_end, tzinfo=zone) + timedelta(days=1)
    return start, end_day


def format_calendar_range(start: datetime, end_exclusive: datetime, zone_name: str) -> str:
    """Explain a date-only official range without pretending a clock time was published."""
    last = end_exclusive - timedelta(seconds=1)
    start_date = start.strftime("%Y-%m-%d")
    last_date = last.strftime("%Y-%m-%d")
    beijing_from = beijing_clock(start)
    beijing_to = beijing_clock(end_exclusive)
    return (
        f"{start_date} 至 {last_date}（官方按{zone_name}公布日期，未写时刻；"
        f"换算到北京时间为 {beijing_from} 至 {beijing_to}，含结束日全天）"
    )


def month_number(name: str) -> int | None:
    return _MONTHS.get(name.lower())
