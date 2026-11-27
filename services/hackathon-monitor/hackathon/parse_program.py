"""BNB Chain hackathon CMS records from the public site JSON."""

from __future__ import annotations

import re

from .classify import classify_index_program
from .model import EventDraft, Link, Milestone, Project
from .textutil import collapse, strip_tags
from .timeutil import as_utc, format_instant_range, parse_naive, parse_zone_label

_PRIVATE_FORM = (
    "forms.gle",
    "docs.google.com/forms",
    "app.binance.com/uni-qr",
    "luma.com",
    "lu.ma",
    "typeform.com",
    "tally.so",
)


def detail_url(slug: str) -> str:
    return f"https://www.bnbchain.org/en/hackathons/{slug}"


def winners_embedded(program: dict) -> bool:
    for layer in program.get("winner_layer") or []:
        if isinstance(layer, dict) and isinstance(layer.get("winners"), list):
            return True
    return False


def program_to_draft(program: dict) -> EventDraft | None:
    slug = (program.get("slug") or "").strip()
    title = collapse(program.get("title") or "", 180)
    if not slug or not title or program.get("publish") is False:
        return None
    source = detail_url(slug)
    classification, reason = classify_index_program(title, program.get("description") or "")
    zone = parse_zone_label(program.get("timezone"))
    start = parse_naive(program.get("start"), zone)
    end = parse_naive(program.get("end"), zone)
    milestones = []
    if zone is None and (program.get("start") or program.get("end")):
        milestones.append(Milestone(
            key="window",
            label="活动时间",
            start_utc=None,
            end_utc=None,
            display="官方给出了时间，但没有可识别的时区，因此不换算。",
            timezone_label=str(program.get("timezone") or ""),
            precision="unknown",
            source_url=source,
        ))
    elif start or end:
        milestones.append(Milestone(
            key="window",
            label="活动时间",
            start_utc=as_utc(start),
            end_utc=as_utc(end),
            display=format_instant_range(start, end, f"来源时区 {program.get('timezone') or 'UTC'}"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=source,
        ))
    _optional_window(milestones, program, "apply_as_hacker_start_time", "apply_as_hacker_end_time", "apply", "报名", zone, source)
    _optional_window(milestones, program, "submit_project_start_time", "submit_project_end_time", "submit", "作品提交", zone, source)

    projects: list[Project] = []
    if winners_embedded(program):
        for index, layer in enumerate(program.get("winner_layer") or []):
            if not isinstance(layer, dict):
                continue
            track = collapse(" / ".join(part for part in (layer.get("layer1"), layer.get("layer2")) if part), 120)
            for winner in layer.get("winners") or []:
                if not isinstance(winner, dict):
                    continue
                name = collapse(winner.get("name") or "", 120)
                if not name:
                    continue
                url = _http(winner.get("demo")) or _http(winner.get("github")) or ""
                projects.append(Project(
                    key=f"winner-{winner.get('id') or name}",
                    name=name,
                    role="winner",
                    place=track,
                    track=track,
                    url=url,
                    source_url=source,
                    note=collapse(strip_tags(winner.get("desc") or ""), 180),
                ))
            if index > 500:
                break

    form = _http(program.get("submit_project_url")) or _http(program.get("apply_as_hacker_url"))
    links = [Link("官方活动页", source)]
    submission_state = "not_published"
    submission_note = "已核对的官方活动页没有公布投稿项目。"
    if form and _is_private_form(form):
        links.append(Link("报名或提交入口（不是公开项目列表）", form))
        if not any(item.role == "submitted" for item in projects):
            submission_state = "private_form"
            submission_note = "官方只给出了报名或提交表单，页面上没有可核验的参赛项目列表。表单不会被当成排行榜。"
    elif form:
        links.append(Link("官方给出的提交链接", form))
        submission_note = "官方给出了提交链接，但没有附带可核验的项目名单。"

    embedded = winners_embedded(program)
    if projects:
        results_state = "published"
        results_note = "以下为官方活动页公布的获奖或入选项目，不是完整投稿名单。"
    elif embedded:
        results_state = "not_published"
        results_note = "官方活动页这次没有公布入选或获奖项目。"
    else:
        results_state = "not_published"
        results_note = "目录页没有附带获奖名单，以活动详情页为准。"

    prize = _prize(program)
    return EventDraft(
        id=f"bnb-hackathon:{slug}",
        title=title,
        classification=classification,
        classification_reason=reason,
        summary=collapse(strip_tags(program.get("description") or program.get("overview") or "")),
        location=_location(program),
        prize=prize,
        official_status=(program.get("status") or None),
        start_utc=as_utc(start),
        end_utc=as_utc(end),
        submission_state=submission_state,
        submission_note=submission_note,
        submission_form_url=form if form and _is_private_form(form) else None,
        results_state=results_state,
        results_note=results_note,
        milestones=milestones,
        projects=projects,
        links=links,
        touch_results=embedded,
    )


def _optional_window(milestones, program, start_key, end_key, key, label, zone, source):
    if zone is None:
        return
    start = parse_naive(program.get(start_key), zone)
    end = parse_naive(program.get(end_key), zone)
    if not start and not end:
        return
    milestones.append(Milestone(
        key=key,
        label=label,
        start_utc=as_utc(start),
        end_utc=as_utc(end),
        display=format_instant_range(start, end),
        timezone_label="Asia/Shanghai",
        precision="instant",
        source_url=source,
    ))


def _location(program: dict) -> str:
    parts = [program.get("location_building"), program.get("location_city"), program.get("location_country")]
    text = "，".join(collapse(str(part), 80) for part in parts if part)
    online = bool(program.get("location_online"))
    if online and text:
        return f"{text}（含线上）"
    if online:
        return "线上"
    return text


def _prize(program: dict) -> str:
    pool = program.get("prize_pool")
    if isinstance(pool, bool) or pool in (None, ""):
        return ""
    if isinstance(pool, (int, float)) and not isinstance(pool, bool):
        amount = int(pool) if float(pool).is_integer() else pool
        return f"官方奖池字段：{amount:,} USD" if isinstance(amount, int) else f"官方奖池字段：{amount} USD"
    return collapse(str(pool), 160)


def _http(value) -> str | None:
    if isinstance(value, str) and value.startswith("http"):
        return value.strip()
    return None


def _is_private_form(url: str) -> bool:
    host = url.lower()
    return any(part in host for part in _PRIVATE_FORM)


def index_programs(page_props: dict) -> list[dict]:
    state = ((page_props or {}).get("initialState") or {}).get("cms") or {}
    programs = state.get("hackathonPrograms")
    if not isinstance(programs, list):
        return []
    return [item for item in programs if isinstance(item, dict)]


def active_program(page_props: dict) -> dict | None:
    state = ((page_props or {}).get("initialState") or {}).get("cms") or {}
    program = state.get("activeHackathonProgram")
    return program if isinstance(program, dict) and program.get("slug") else None


_UPDATED = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def updated_marker(program: dict) -> str:
    value = program.get("date_updated") or ""
    return value if isinstance(value, str) and _UPDATED.search(value) else ""
