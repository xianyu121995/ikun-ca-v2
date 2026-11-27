"""Binance public announcement articles. Times are converted to Beijing time."""

from __future__ import annotations

import re

from .classify import mentions_hackathon
from .model import EventDraft, Link, Milestone
from .textutil import collapse, rich_text
from .timeutil import BEIJING, UTC, as_utc, format_instant_range, parse_naive

_CN = re.compile(
    r"(?P<label>作品提交期|评审期|公示期)\s*[:：]\s*"
    r"(?P<y1>\d{4})年(?P<mo1>\d{1,2})月(?P<d1>\d{1,2})日\s*(?P<h1>\d{2}):(?P<mi1>\d{2}):(?P<s1>\d{2})"
    r"\s*至\s*"
    r"(?P<y2>\d{4})年(?P<mo2>\d{1,2})月(?P<d2>\d{1,2})日\s*(?P<h2>\d{2}):(?P<mi2>\d{2}):(?P<s2>\d{2})"
    r"\s*（东八区时间）"
)
_EN = re.compile(
    r"(?P<label>Submission Period|Internal Review Period|Public Review Period)\s*:?\s*"
    r"(?P<start>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \(UTC\)\s*to\s*"
    r"(?P<end>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \(UTC\)",
    re.I,
)
_LABELS = {
    "作品提交期": ("submission", "作品提交"),
    "评审期": ("review", "评审"),
    "公示期": ("announcement", "公示"),
    "submission period": ("submission", "作品提交"),
    "internal review period": ("review", "评审"),
    "public review period": ("announcement", "公示"),
}
_PRIZE = re.compile(r"(?:总奖励为|total rewards?(?: of)?|win)\s*([\d,]+)\s*USDC", re.I)
_PRIZE_LOOSE = re.compile(r"([\d,]{4,})\s*USDC", re.I)


def article_urls(code: str) -> tuple[str, str]:
    return (
        f"https://www.binance.com/zh-CN/support/announcement/detail/{code}",
        f"https://www.binance.com/en/support/announcement/detail/{code}",
    )


def parse_article(payload: dict, code: str, lang: str) -> dict | None:
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    title = collapse(data.get("title") or "", 200)
    if not title or not mentions_hackathon(title):
        return None
    text, links = rich_text(data.get("body"))
    milestones = _milestones(text, lang)
    zh, en = article_urls(code)
    source = zh if lang.lower().startswith("zh") else en
    return {
        "title": title,
        "text": text,
        "links": links,
        "milestones": milestones,
        "source": source,
        "lang": lang,
        "prize": _prize(title, text),
    }


def merge_articles(code: str, zh: dict | None, en: dict | None) -> EventDraft | None:
    primary = zh or en
    if primary is None:
        return None
    zh_url, en_url = article_urls(code)
    milestones = _prefer_milestones(zh, en, zh_url, en_url)
    conflict = _conflict(zh, en)
    form, community = _forms((zh or {}).get("links") or [], (en or {}).get("links") or [])
    links = [Link("中文公告", zh_url), Link("英文公告", en_url)]
    if form:
        links.append(Link("作品提交表单（不是公开项目列表）", form))
    if community and community != form:
        links.append(Link("社区传播提交（不是参赛项目列表）", community))
    if form:
        submission_state = "private_form"
        submission_note = "公告里的提交入口是币安问卷。问卷不是公开项目库，未公布的投稿不会显示在这里。"
    else:
        submission_state = "not_published"
        submission_note = "公告没有给出可核验的投稿项目列表。"
    start, end = _bounds(milestones, "submission")
    if start is None:
        start, end = _bounds(milestones, "window")
    note = "中英文公告的时刻不一致，页面同时保留两套来源，不自行取舍。" if conflict else ""
    return EventDraft(
        id=f"binance:{code}",
        title=primary["title"],
        classification="hackathon",
        classification_reason="币安公告标题写明这是黑客松。",
        summary=_intro(primary.get("text") or ""),
        prize=primary.get("prize") or (en or zh or {}).get("prize") or "",
        official_status=None,
        start_utc=start,
        end_utc=_bounds(milestones, "announcement")[1] or end,
        submission_state=submission_state,
        submission_note=submission_note,
        submission_form_url=form,
        results_state="not_published",
        results_note="这份公告没有公布入选或获奖项目。公开之后会从同一条公告或后续官方来源补上。",
        milestones=milestones,
        links=links,
        location="线上",
    ) if not note else _with_conflict(primary, code, milestones, links, form, community, submission_state, submission_note, note)


def _with_conflict(primary, code, milestones, links, form, community, submission_state, submission_note, note):
    zh_url, en_url = article_urls(code)
    start, end = _bounds(milestones, "submission")
    draft = EventDraft(
        id=f"binance:{code}",
        title=primary["title"],
        classification="hackathon",
        classification_reason="币安公告标题写明这是黑客松。",
        summary=note,
        prize=primary.get("prize") or "",
        start_utc=start,
        end_utc=_bounds(milestones, "announcement")[1] or end,
        submission_state=submission_state,
        submission_note=submission_note,
        submission_form_url=form,
        results_state="not_published",
        results_note="这份公告没有公布入选或获奖项目。",
        milestones=milestones,
        links=links,
        location="线上",
    )
    draft.links = [link for link in links if link.url in {zh_url, en_url, form, community}]
    return draft


def _milestones(text: str, lang: str) -> list[Milestone]:
    found: list[Milestone] = []
    flat = re.sub(r"\s+", " ", text)
    if lang.lower().startswith("zh"):
        for match in _CN.finditer(flat):
            key, label = _LABELS[match.group("label")]
            start = parse_naive(_stamp(match, "1"), BEIJING)
            end = parse_naive(_stamp(match, "2"), BEIJING)
            found.append(_milestone(key, label, start, end, "公告写明东八区时间。"))
        return found
    for match in _EN.finditer(flat):
        key, label = _LABELS[match.group("label").lower()]
        start = parse_naive(match.group("start"), UTC)
        end = parse_naive(match.group("end"), UTC)
        found.append(_milestone(key, label, start, end, "英文公告写明 UTC，已换算为北京时间。"))
    return found


def _stamp(match: re.Match, side: str) -> str:
    return (
        f"{match.group('y' + side)}-{int(match.group('mo' + side)):02d}-{int(match.group('d' + side)):02d} "
        f"{match.group('h' + side)}:{match.group('mi' + side)}:{match.group('s' + side)}"
    )


def _milestone(key, label, start, end, note) -> Milestone:
    return Milestone(
        key=key,
        label=label,
        start_utc=as_utc(start),
        end_utc=as_utc(end),
        display=format_instant_range(start, end, note),
        timezone_label="Asia/Shanghai",
        precision="instant",
        source_url="",
    )


def _prefer_milestones(zh, en, zh_url, en_url) -> list[Milestone]:
    zh_items = list((zh or {}).get("milestones") or [])
    en_items = list((en or {}).get("milestones") or [])
    for item in zh_items:
        item.source_url = zh_url
    for item in en_items:
        item.source_url = en_url
    if not zh_items:
        return en_items
    if not en_items:
        return zh_items
    zh_map = {item.key: (item.start_utc, item.end_utc) for item in zh_items}
    en_map = {item.key: (item.start_utc, item.end_utc) for item in en_items}
    if zh_map == en_map:
        return zh_items
    merged = []
    for item in zh_items:
        copy = Milestone(**{**item.__dict__, "key": f"zh-{item.key}"})
        merged.append(copy)
    for item in en_items:
        copy = Milestone(**{**item.__dict__, "key": f"en-{item.key}", "label": f"{item.label}（英文）"})
        merged.append(copy)
    return merged


def _conflict(zh, en) -> bool:
    if not zh or not en:
        return False
    zh_map = {item.key: (item.start_utc, item.end_utc) for item in zh["milestones"]}
    en_map = {item.key: (item.start_utc, item.end_utc) for item in en["milestones"]}
    shared = set(zh_map) & set(en_map)
    return any(zh_map[key] != en_map[key] for key in shared)


def _bounds(milestones: list[Milestone], key: str) -> tuple[str | None, str | None]:
    for item in milestones:
        if item.key == key or item.key.endswith(key):
            return item.start_utc, item.end_utc
    return None, None


def _forms(*groups: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    form = None
    community = None
    for group in groups:
        for label, href in group:
            if "app.binance.com/uni-qr/user-survey" not in href and "forms.gle" not in href and "docs.google.com/forms" not in href:
                continue
            blob = f"{label} {href}"
            if any(word in blob for word in ("X 链接", "X link", "hashtag", "社区传播")):
                community = community or href
            elif any(word in blob for word in ("提交作品", "Submit", "作品提交", "survey")):
                form = form or href
            else:
                form = form or href
    return form, community


def _intro(text: str) -> str:
    head = re.split(r"作品提交期|Submission Period", text, maxsplit=1)[0]
    head = re.sub(r"这是一般性公告.*?亲爱的用户：\s*", "", head, flags=re.S)
    head = re.sub(r"This is a general announcement.*?Binancians,?\s*", "", head, flags=re.S | re.I)
    return collapse(head, 180)


def _prize(title: str, text: str) -> str:
    match = _PRIZE.search(title) or _PRIZE.search(text) or _PRIZE_LOOSE.search(title)
    if not match:
        return ""
    return f"官方公告奖励：{match.group(1)} USDC"
