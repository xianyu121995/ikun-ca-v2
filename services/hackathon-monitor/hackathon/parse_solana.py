"""Solana Foundation hackathon hub: https://hackathons.solana.com/hackathons."""

from __future__ import annotations

import re

from .model import EventDraft, Link, Milestone, Project
from .textutil import collapse, strip_tags
from .timeutil import as_utc, format_instant_range, parse_iso

_DATE = re.compile(r"\$D(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")
_STATUS = re.compile(r'\\"status\\":\\"(?P<status>winner|submitted|selected|shortlisted)\\",\\"is_public\\":(?P<public>true|false)')
_GITHUB = re.compile(r'\\"github_url\\":(?:null|\\"(?P<url>https://[^\\"]+)\\")')
_DEMO = re.compile(r'\\"demo_url\\":(?:null|\\"(?P<url>https://[^\\"]+)\\")')


def hub_url() -> str:
    return "https://hackathons.solana.com/hackathons"


def detail_url(slug: str) -> str:
    return f"https://hackathons.solana.com/hackathons/{slug}"


def _unescape(value: str) -> str:
    return value.replace("\\n", " ").replace('\\"', '"').replace("\\\\", "\\")


def _payload(page: str) -> str:
    return "".join(re.findall(r"self\.__next_f\.push\((.*?)\)\s*</script>", page or "", re.S))


def _instant(raw: str | None):
    if not raw:
        return None
    match = _DATE.search(raw)
    return parse_iso(match.group(1)) if match else parse_iso(raw.removeprefix("$D"))


def parse_hub(page: str) -> list[dict]:
    """One record per slug. Dates stay null when the page has not published them."""
    payload = _payload(page)
    found = []
    seen = set()
    pieces = re.split(r'\\"slug\\":\\"', payload)
    for index, piece in enumerate(pieces[1:], start=1):
        slug_match = re.match(r"([a-z0-9-]+)", piece)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        if slug in seen or slug in {"add-bounty"}:
            continue
        before = pieces[index - 1]
        after = piece.split('\\"title\\":', 1)[0][:2000]
        titles = re.findall(r'\\"title\\":\\"([^\\"]*)\\"', before)
        title = _unescape(titles[-1]) if titles else ""
        descriptions = re.findall(r'\\"description\\":\\"([^\\"]*)\\"', before)
        status_match = re.search(r'\\"status\\":\\"([^\\"]+)\\"', after)
        status = status_match.group(1) if status_match else ""
        if not title or not status or title in {"Next.Metadata", "description", "twitter:title"}:
            continue
        def field_instant(name, text):
            match = re.search(r'\\"' + name + r'\\":(?:null|\\"([^\\"]*)\\")', text)
            return _instant(match.group(1) if match and match.group(1) else None)
        seen.add(slug)
        found.append({
            "slug": slug,
            "title": title,
            "description": _unescape(descriptions[-1]) if descriptions else "",
            "status": status,
            "launch": field_instant("launch_date", after),
            "submission": field_instant("submission_deadline", after),
            "judging": field_instant("judging_deadline", after),
            "completed": field_instant("completed_at", after),
            "prizes": _prizes(after),
        })
    return found


def _prizes(window: str) -> list[tuple[str, int]]:
    pairs = re.findall(r'\\"label\\":\\"(?P<label>[^\\"]+)\\",\\"amount_usdc\\":(?P<amount>\d+)', window)
    prizes = []
    seen = set()
    for label, amount in pairs:
        text = _unescape(label)
        if text in seen:
            continue
        seen.add(text)
        value = int(amount)
        # The public page shows these figures as dollars; the field is 100x larger.
        dollars = value // 100 if value % 100 == 0 and value >= 100 else value
        prizes.append((text, dollars))
    return prizes


def hub_to_draft(record: dict) -> EventDraft:
    source = detail_url(record["slug"])
    milestones = []
    if record["launch"] or record["submission"]:
        milestones.append(Milestone(
            key="window",
            label="开赛至截稿",
            start_utc=as_utc(record["launch"]),
            end_utc=as_utc(record["submission"]),
            display=format_instant_range(record["launch"], record["submission"], "Solana 黑客松站公布的时刻"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=source,
        ))
    if record["judging"]:
        milestones.append(Milestone(
            key="judging",
            label="评审截止",
            start_utc=None,
            end_utc=as_utc(record["judging"]),
            display=format_instant_range(None, record["judging"], "Solana 黑客松站公布的评审截止"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=source,
        ))
    prize = ""
    if record["prizes"]:
        prize = "官方主赛道：" + "；".join(f"{label} {amount:,} USDC" for label, amount in record["prizes"])
    status = record["status"]
    if status == "funding" and not record["launch"]:
        summary = "官方状态是筹奖池。页面没有公布开赛或截稿时间。"
    else:
        summary = collapse(record["description"], 280)
    return EventDraft(
        id=f"solana-hackathon:{record['slug']}",
        title=collapse(record["title"], 180),
        classification="hackathon",
        classification_reason="来自 Solana Foundation 的黑客松站。",
        ecosystem="solana",
        summary=summary,
        location="线上",
        prize=prize,
        official_status=status,
        start_utc=as_utc(record["launch"]),
        end_utc=as_utc(record["submission"] or record["completed"] or record["judging"]),
        submission_state="not_published",
        submission_note="活动页还没有公开投稿名单。注册人数不是项目列表。",
        results_state="not_published",
        results_note="活动页还没有公布入选或获奖项目。",
        milestones=milestones,
        links=[Link("Solana 黑客松站", source), Link("黑客松目录", hub_url())],
    )


def parse_detail_projects(page: str, slug: str) -> tuple[list[Project], str, str]:
    """Public projects only. is_public false stays out unless the visible page names that project."""
    source = detail_url(slug)
    payload = _payload(page)
    visible = strip_tags(re.sub(r"(?is)<script[^>]*>.*?</script>", " ", page or ""))
    projects = []
    seen = set()
    hidden = 0
    for chunk in payload.split('\\"project_name\\":\\"')[1:]:
        name = collapse(_unescape(chunk.split('\\"', 1)[0]), 120)
        body = chunk.split('\\"project_name\\":', 1)[0]
        status_match = _STATUS.search(body)
        if not name or not status_match:
            continue
        public = status_match.group("public") == "true"
        named = name.lower() in visible.lower()
        status = status_match.group("status")
        if status == "winner" and (public or named):
            role = "winner"
        elif public and status != "winner":
            role = "submitted"
        else:
            hidden += 1
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        github = (_GITHUB.search(body).group("url") if _GITHUB.search(body) and _GITHUB.search(body).group("url") else "")
        demo_match = _DEMO.search(body)
        demo = demo_match.group("url") if demo_match and demo_match.group("url") else ""
        projects.append(Project(
            key=f"{role}-{key}",
            name=name,
            role=role,
            place="",
            track="",
            url=demo or github or "",
            source_url=source,
        ))
    if not projects and hidden:
        note = f"页面数据里有 {hidden} 个未公开项目。未公开的不列出，所以这里不是全部投稿。"
    elif projects and hidden:
        note = f"下面只包括官方标成公开、或页面正文点名的项目。另有 {hidden} 个未公开记录没有列出，这不是全部投稿。"
    elif projects:
        note = "下面是官方标成公开的项目。页面没有声明这就是每一份报名。"
    else:
        note = "活动页没有公开投稿名单。注册人数或空的提交计数都不是项目列表。"
    winners = [item for item in projects if item.role == "winner"]
    results = "下面是页面点名的获奖项目，不是全部投稿。" if winners else "活动页还没有公布入选或获奖项目。"
    return projects, note, results


def _url(raw: str) -> str:
    if not raw or raw == "null":
        return ""
    text = _unescape(raw.strip('"'))
    return text if text.startswith("http") else ""
