"""BNB Chain blog posts that announce a hackathon or name its winners."""

from __future__ import annotations

import re

from .classify import blog_role, mentions_hackathon
from .model import EventDraft, Link, Milestone, Project
from .textutil import article_fragment, collapse, html_tables, strip_tags
from .timeutil import (
    BANGKOK,
    as_utc,
    calendar_span,
    format_calendar_range,
    format_instant_range,
    month_number,
    parse_iso,
)

_RANGE = re.compile(
    r"(?P<m1>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<d1>\d{1,2})\s*[–—-]\s*"
    r"(?:(?P<m2>January|February|March|April|May|June|July|August|September|October|November|December)\s+)?"
    r"(?P<d2>\d{1,2}),\s*(?P<y>\d{4})",
    re.I,
)
_CLOCK = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<day>\d{1,2}),\s*from\s+(?P<h1>\d{1,2}):(?P<mi1>\d{2})\s*[–—-]\s*(?P<h2>\d{1,2}):(?P<mi2>\d{2})",
    re.I,
)
_MONTH_DAY = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<day>\d{1,2})",
    re.I,
)
_PLACE = re.compile(
    r"(?P<place>\d+(?:st|nd|rd|th)\s+Place|Winner)\s*\((?P<prize>[^)]{1,40})\)\s*:\s*(?P<name>[A-Za-z0-9][A-Za-z0-9 ._+#-]{0,60})",
    re.I,
)
_TRACK = re.compile(r"^(?:Main Track Winners.*|Best Use of .+|.+ Winners: .+)$", re.I)
_PRIVATE = ("luma.com", "lu.ma", "forms.gle", "docs.google.com/forms", "app.binance.com/uni-qr", "typeform.com")


def post_url(slug: str) -> str:
    return f"https://www.bnbchain.org/en/blog/{slug}"


def parse_post(html: str, slug: str, title: str = "", excerpt: str = "") -> EventDraft | None:
    fragment = article_fragment(html or "")
    text = strip_tags(fragment)
    heading = _heading(fragment) or title
    role = blog_role(heading or title, excerpt or text[:500])
    if role is None and not mentions_hackathon(text[:800], excerpt):
        return None
    if role is None:
        role = "results" if re.search(r"winning projects|winners", text[:400], re.I) else "event"
    source = post_url(slug)
    published = _published(html)
    if role == "results":
        return _results_draft(slug, heading or title, text, source, published)
    return _event_draft(slug, heading or title, text, fragment, source, published, excerpt)


def _event_draft(slug, title, text, fragment, source, published, excerpt) -> EventDraft:
    zone = BANGKOK if re.search(r"bangkok|park hyatt", text, re.I) else None
    milestones: list[Milestone] = []
    start_utc = end_utc = None
    match = _RANGE.search(text)
    if match and zone is not None:
        start, end = calendar_span(
            int(match.group("y")),
            month_number(match.group("m1")) or 1,
            int(match.group("d1")),
            int(match.group("d2")),
            month_number(match.group("m2")) if match.group("m2") else None,
            zone,
        )
        start_utc, end_utc = as_utc(start), as_utc(end)
        milestones.append(Milestone(
            key="window",
            label="活动日期",
            start_utc=start_utc,
            end_utc=end_utc,
            display=format_calendar_range(start, end, "曼谷时间（UTC+7）"),
            timezone_label="Asia/Shanghai",
            precision="date",
            source_url=source,
        ))
    year = int(match.group("y")) if match else (published.year if published else None)
    clock = _CLOCK.search(text)
    if clock and year and zone is not None:
        month = month_number(clock.group("month")) or 1
        from datetime import datetime
        begin = datetime(year, month, int(clock.group("day")), int(clock.group("h1")), int(clock.group("mi1")), tzinfo=zone)
        finish = datetime(year, month, int(clock.group("day")), int(clock.group("h2")), int(clock.group("mi2")), tzinfo=zone)
        milestones.append(Milestone(
            key="demo-night",
            label="Demo Night",
            start_utc=as_utc(begin),
            end_utc=as_utc(finish),
            display=format_instant_range(begin, finish, "源文为曼谷当地时间"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=source,
        ))
    if year and zone is not None:
        milestones.extend(_key_dates(fragment, year, zone, source))
    links, form = _links(fragment, source)
    prize = _prize(fragment)
    location = "Park Hyatt Bangkok，曼谷" if re.search(r"park hyatt bangkok", text, re.I) else ("曼谷" if zone else "")
    projects = _winner_projects(text, source, "")
    if form:
        submission_state = "private_form"
        submission_note = "官方给出的是报名或申请入口，不是公开的参赛项目列表。"
    else:
        submission_state = "not_published"
        submission_note = "这篇官方博客没有公布投稿项目。"
    if projects:
        results_state, results_note = "published", "以下名称来自这篇官方博客，不是完整投稿名单。"
    else:
        results_state, results_note = "not_published", "这篇官方博客还没有公布入选或获奖项目。"
    return EventDraft(
        id=f"bnb-blog:{slug}",
        title=collapse(title, 180),
        classification="hackathon",
        classification_reason="BNB Chain 官方博客把这篇文章称为黑客松。",
        summary=collapse(excerpt or text, 360),
        location=location,
        prize=prize,
        official_status=None,
        start_utc=start_utc,
        end_utc=end_utc,
        submission_state=submission_state,
        submission_note=submission_note,
        submission_form_url=form,
        results_state=results_state,
        results_note=results_note,
        milestones=milestones,
        projects=projects,
        links=links,
    )


def _results_draft(slug, title, text, source, published) -> EventDraft:
    projects = _winner_projects(text, source, "")
    return EventDraft(
        id=f"bnb-blog:{slug}",
        title=collapse(title, 180),
        classification="hackathon",
        classification_reason="BNB Chain 官方博客公布了黑客松结果。",
        summary=collapse(text, 280),
        results_state="published" if projects else "not_published",
        results_note="以下为官方点名的获奖项目，博客没有给出其余投稿。" if projects else "标题像结果公布，但没有解析到具体项目名称。",
        submission_state="not_published",
        submission_note="结果公告点名的是获奖项目，不是可核验的全部投稿。",
        projects=projects,
        links=[Link("官方结果", source)],
        milestones=[],
    )


def _winner_projects(text: str, source: str, default_track: str) -> list[Project]:
    track = default_track
    projects = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _TRACK.search(line) and not _PLACE.search(line):
            track = collapse(line, 120)
            continue
        match = _PLACE.search(line)
        if not match:
            continue
        name = collapse(match.group("name"), 80)
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        projects.append(Project(
            key=f"winner-{key}",
            name=name,
            role="winner",
            place=collapse(match.group("place"), 40),
            track=track,
            url="",
            source_url=source,
            note=collapse(match.group("prize"), 40),
        ))
    return projects


def _key_dates(fragment: str, year: int, zone, source: str) -> list[Milestone]:
    milestones = []
    for table in html_tables(fragment):
        header = " ".join(table[0]).lower()
        if "date" not in header or "stage" not in header:
            continue
        for cells in table[1:]:
            found = _MONTH_DAY.search(cells[0])
            if not found:
                continue
            month = month_number(found.group("month"))
            if not month:
                continue
            start, end = calendar_span(year, month, int(found.group("day")), int(found.group("day")), None, zone)
            label = cells[1] if len(cells) > 1 else "官方日程"
            note = cells[2] if len(cells) > 2 else ""
            milestones.append(Milestone(
                key="date-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40],
                label=label,
                start_utc=as_utc(start),
                end_utc=as_utc(end),
                display=format_calendar_range(start, end, "曼谷时间（UTC+7）") + (f"。官方说明：{note}" if note else ""),
                timezone_label="Asia/Shanghai",
                precision="date",
                source_url=source,
            ))
    return milestones


def _links(fragment: str, source: str) -> tuple[list[Link], str | None]:
    links = [Link("官方博客", source)]
    form = None
    for href in re.findall(r'(?i)href="(https?://[^"]+)"', fragment):
        if any(part in href for part in _PRIVATE):
            if form is None:
                form = href
            links.append(Link("报名或申请入口（不是项目列表）", href))
    # de-dupe
    unique = []
    seen = set()
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        unique.append(link)
    return unique, form


def _prize(fragment: str) -> str:
    lines = []
    for table in html_tables(fragment):
        for cells in table:
            if cells and re.search(r"^(1st|2nd|3rd)$", cells[0], re.I) and any("$" in cell for cell in cells):
                lines.append(" ".join(cells[:3]))
    if not lines:
        return ""
    return "官方博客奖项：" + "；".join(lines[:6])


def _heading(fragment: str) -> str:
    match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", fragment or "")
    return collapse(strip_tags(match.group(1)), 180) if match else ""


def _published(page: str):
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page or "")
    return parse_iso(match.group(1)) if match else None


def listing_posts(page_props: dict) -> tuple[list[dict], int]:
    post_data = (((page_props or {}).get("initialState") or {}).get("base") or {}).get("postData") or {}
    posts = post_data.get("data") if isinstance(post_data, dict) else None
    pages = ((post_data.get("meta") or {}).get("pagination") or {}).get("pages") if isinstance(post_data, dict) else None
    if not isinstance(posts, list):
        return [], 0
    clean = []
    for post in posts:
        if isinstance(post, dict) and post.get("slug") and post.get("title"):
            clean.append({
                "slug": post["slug"],
                "title": post.get("title") or "",
                "excerpt": post.get("excerpt") or "",
                "published_at": post.get("published_at") or "",
            })
    return clean, int(pages or 0)
