"""Colosseum's public product directory. Descriptions and team members are not stored."""

from __future__ import annotations

from .model import EventDraft, Link, Milestone, Project
from .textutil import collapse
from .timeutil import as_utc, format_instant_range, parse_iso

DIRECTORY = "https://api.colosseum.com/api/projects/directories"
PROJECTS = "https://api.colosseum.com/api/projects"
ETERNAL_PAGE = "https://colosseum.com/eternal"


def projects_page_url(hackathon_id: int, offset: int, chain: str | None, limit: int = 50) -> str:
    query = f"sort=NAME&hackathonIds[]={hackathon_id}&limit={limit}&offset={offset}"
    if chain:
        query += f"&chains[]={chain}"
    return f"{PROJECTS}?{query}"


def directory_url(hackathon_id: int) -> str:
    return f"https://colosseum.com/arena/projects/explore?hackathonId={hackathon_id}"


def project_url(slug: str) -> str:
    return f"https://colosseum.com/projects/{slug}" if slug else ""


def hackathon_to_draft(record: dict, total: int | None, solana_only: bool) -> EventDraft:
    source = record.get("landingPageUrl") or directory_url(record["id"])
    start = parse_iso(record.get("startDate"))
    submission_start = parse_iso(record.get("projectSubmissionStartDate"))
    submission_end = parse_iso(record.get("projectSubmissionEndDate"))
    end = parse_iso(record.get("endDate")) or submission_end
    milestones = []
    if start or end:
        milestones.append(Milestone(
            key="window",
            label="活动时间",
            start_utc=as_utc(start),
            end_utc=as_utc(end),
            display=format_instant_range(start, end, "Colosseum 公开目录接口里的时间"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=DIRECTORY,
        ))
    if submission_start or submission_end:
        milestones.append(Milestone(
            key="submit",
            label="作品提交",
            start_utc=as_utc(submission_start),
            end_utc=as_utc(submission_end),
            display=format_instant_range(submission_start, submission_end, "Colosseum 公开目录接口里的提交窗口"),
            timezone_label="Asia/Shanghai",
            precision="instant",
            source_url=DIRECTORY,
        ))
    if solana_only and total is not None:
        note = f"公开目录里链字段为 Solana 的项目会列在下面。整个目录还有其他链，那些不算进这份 Solana 名单。目录总数见本次核对说明。"
    elif total == 0:
        note = "Colosseum 公开目录这次没有返回项目。"
    else:
        note = "下面是 Colosseum 公开产品目录里的项目。目录没有分链字段。没进目录的投稿不会出现，所以这仍不是每一份报名表。"
    return EventDraft(
        id=f"colosseum:{record.get('slug') or record['id']}",
        title=collapse(record.get("name") or "", 180),
        classification="hackathon",
        classification_reason="Colosseum 公开黑客松目录。Colosseum 是 Solana 生态的官方黑客松主办方。",
        ecosystem="solana",
        summary=collapse(record.get("description") or "", 240),
        location="线上",
        official_status=None,
        start_utc=as_utc(start),
        end_utc=as_utc(end),
        submission_state="public" if total else "not_published",
        submission_note=note,
        results_state="not_published",
        results_note="这份目录接口没有单独给出获奖标记。获奖项目只有在记录里带有奖项字段时才会标成获奖。",
        milestones=milestones,
        links=[Link("活动页", source), Link("公开项目目录", directory_url(record["id"]))],
    )


def eternal_draft() -> EventDraft:
    return EventDraft(
        id="colosseum:eternal",
        title="Colosseum Eternal",
        classification="hackathon",
        classification_reason="Colosseum 把 Eternal 写成两次主黑客松之间的常设黑客松。",
        ecosystem="solana",
        summary="常设的四周冲刺。官方页面写明 Eternal Award 为 25,000 美元非稀释稳定币。页面没有给出当前这一期的开赛和截稿钟点。",
        prize="官方页面：Eternal Award 25,000 美元非稀释稳定币",
        location="线上",
        submission_state="not_published",
        submission_note="官方 FAQ 写明投稿默认会出现在 Colosseum 目录里，但这次没有拿到不需要登录的完整列表。没核到的项目不会显示。",
        results_state="not_published",
        results_note="页面说明每期会选出获奖团队，但没有在这份公开页面列出当前获奖名单。",
        links=[Link("Eternal 说明", ETERNAL_PAGE)],
    )


def projects_from_page(payload: dict, solana_only: bool) -> tuple[list[Project], int | None]:
    projects = []
    for item in payload.get("projects") or []:
        if not isinstance(item, dict):
            continue
        name = collapse(item.get("name") or "", 160)
        slug = item.get("slug") or ""
        if not name:
            continue
        prize = item.get("prize")
        role = "winner" if prize not in (None, "", [], {}) else "submitted"
        place = collapse(str(prize), 80) if role == "winner" else ""
        url = item.get("website") or item.get("repoLink") or ""
        if not isinstance(url, str) or not url.startswith("http"):
            url = ""
        projects.append(Project(
            key=f"colosseum-{item.get('id') or slug or name}",
            name=name,
            role=role,
            place=place,
            track="",
            url=url,
            source_url=project_url(slug) or directory_url(item.get("hackathonId") or 0),
        ))
    total = payload.get("totalCount")
    return projects, total if isinstance(total, int) else None
