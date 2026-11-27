"""Read the same public event, project, and award data as HackQuest's gallery."""

from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


API = "https://api.hackquest.io/graphql"
DIRECTORY = "https://www.hackquest.io/hackathons"
FLIGHT = re.compile(r"self\.__next_f\.push\(")
EVENT_DATA = re.compile(r'"findUniqueHackathon"\s*:\s*')
BSC_CHAIN = re.compile(r"\b(?:BNB\s+(?:Smart\s+)?Chain|BSC)\b", re.I)
SOL_CHAIN = re.compile(r"\bSolana\b", re.I)
EVENTS = """
query ListHackathons($page: Int, $limit: Int, $where: HackathonWhereInput) {
  listHackathons(page: $page, limit: $limit, where: $where) {
    total
    data { name alias status announce currentStatus ecosystem { type } info { host intro }
           timeline { registrationOpen submissionOpen submissionClose rewardTime } }
  }
}
"""
PROJECTS = """
query HackathonProjects($filter: ProjectFilterInput!, $page: Int, $limit: Int) {
  projects(filter: $filter, page: $page, limit: $limit) {
    total
    data { id alias name tracks description projectLinks }
  }
}
"""
REWARDS = """
query FindHackathonReward($hackathonId: String!) {
  findHackathonReward(hackathonId: $hackathonId) {
    announce id name rewardName
    projects { id alias name tracks description projectLinks winner { rewardId place } }
  }
}
"""


def event_metadata(url, html):
    alias = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
    decoder = json.JSONDecoder()
    stream = []
    for marker in FLIGHT.finditer(html):
        try:
            chunk, _ = decoder.raw_decode(html, marker.end())
        except ValueError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and chunk[0] == 1 and isinstance(chunk[1], str):
            stream.append(chunk[1])
    decoded = "".join(stream)
    for marker in EVENT_DATA.finditer(decoded):
        try:
            event, _ = decoder.raw_decode(decoded, marker.end())
        except ValueError:
            continue
        if (isinstance(event, dict) and event.get("id") and
                str(event.get("alias", "")).casefold() == alias.casefold()):
            return event
    raise ValueError("HackQuest 页面未提供可核实的赛事数据")


def moment(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def lifecycle(event, now, catalog=False):
    if event.get("announce") is True:
        return "completed"
    states = set(event.get("currentStatus") or [])
    dates = event.get("timeline") or {}
    opens = moment(dates.get("registrationOpen") or dates.get("submissionOpen"))
    closes = moment(dates.get("submissionClose"))
    reward = moment(dates.get("rewardTime"))
    if opens and opens > now:
        return "scheduled"
    if closes and closes > now:
        return "active"
    if "VOTING" in states or "JUDGING" in states:
        return "awaiting_results"
    if closes and closes <= now and event.get("announce") is False:
        if not catalog or (reward and reward >= now - timedelta(days=7)):
            return "awaiting_results"
    return "unknown"


def event_chains(name, description, ecosystem):
    platforms = " ".join(str(item.get("type") or "") for item in ecosystem if isinstance(item, dict))
    text = " ".join((name, description, platforms))
    tags = []
    if BSC_CHAIN.search(text) or re.search(r"\bBNB\b", name, re.I):
        tags.append("BSC")
    if SOL_CHAIN.search(text):
        tags.append("SOL")
    return tags


def parse_hackquest(url, html):
    event = event_metadata(url, html)
    timeline = event.get("timeline") or {}
    schedule = []
    for field, kind, label in (
        ("submissionClose", "submission_close", "HackQuest 提交截止"),
        ("rewardTime", "results_expected", "HackQuest 预计公布获奖名单"),
    ):
        value = timeline.get(field)
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo:
            schedule.append({"kind": kind, "label": label, "time": parsed.isoformat(),
                             "precision": "datetime"})
    return {
        "name": event.get("name"), "platform_event_id": event["id"],
        "event_status": lifecycle(event, datetime.now(timezone.utc)),
        "platform_project_count": event.get("projectCount"), "schedule": schedule,
        "submission_status": "unverified", "winner_status": "unverified",
        "submissions": [], "winners": [],
    }


def graphql(query, variables, timeout):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(API, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/graphql-response+json",
        "Origin": "https://www.hackquest.io", "User-Agent": "BSC-Hackathon-Monitor/1.0",
    })
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("errors") or not isinstance(payload.get("data"), dict):
        raise ValueError("HackQuest 公开查询没有返回可用数据")
    return payload["data"]


def discover_hackquest(timeout=15):
    filters = [{"name": {"contains": phrase, "mode": "insensitive"}}
               for phrase in ("BNB", "BSC", "Solana")]
    filters.extend({"info": {"is": {field: {"contains": phrase, "mode": "insensitive"}}}}
                   for field in ("host", "intro")
                   for phrase in ("BNB Chain", "BNB Smart Chain", "BSC", "Solana"))
    found, page, limit = {}, 1, 20
    now = datetime.now(timezone.utc)
    while True:
        data = graphql(EVENTS, {"page": page, "limit": limit, "where": {"OR": filters}},
                       timeout).get("listHackathons")
        if (not isinstance(data, dict) or type(data.get("total")) is not int or
                not isinstance(data.get("data"), list)):
            raise ValueError("HackQuest 赛事目录未返回可核实的数据")
        for entry in data["data"]:
            name, alias = entry.get("name"), entry.get("alias")
            if not isinstance(name, str) or not isinstance(alias, str) or entry.get("status") != "publish":
                continue
            info = entry.get("info") or {}
            description = " ".join(str(info.get(field) or "") for field in ("host", "intro"))
            chains = event_chains(name, description, entry.get("ecosystem") or [])
            if not chains:
                continue
            row = {"name": name, "url": DIRECTORY + "/" + quote(alias, safe=""), "kind": "hackquest",
                   "chain": chains, "event_status": lifecycle(entry, now, catalog=True)}
            registration = (entry.get("timeline") or {}).get("registrationOpen")
            if isinstance(registration, str) and len(registration) >= 4 and registration[:4].isdigit():
                row["event_year"] = int(registration[:4])
            found[alias] = row
        if page * limit >= data["total"]:
            return list(found.values())
        if not data["data"]:
            raise ValueError("HackQuest 赛事目录的分页结果不完整")
        page += 1


def project(row):
    if not isinstance(row, dict):
        raise ValueError("HackQuest 项目条目格式改变")
    identity, name, alias = (row.get(key) for key in ("id", "name", "alias"))
    if not all(isinstance(value, str) and value.strip() for value in (identity, name, alias)):
        raise ValueError("HackQuest 项目条目缺少 ID、名称或链接")
    tracks = row.get("tracks")
    labels = [item if isinstance(item, str) else item.get("name")
              for item in tracks or [] if isinstance(item, (str, dict))] if isinstance(tracks, list) else []
    labels = [label for label in labels if isinstance(label, str) and label.strip()
              and not re.fullmatch(r"[0-9a-fA-F-]{32,36}", label)]
    item = {"id": identity, "name": name.strip(), "category": ", ".join(labels) or None,
            "url": "https://www.hackquest.io/projects/" + quote(alias, safe="")}
    info, website, twitter = _profile(row.get("description"))
    site, handle = _structured_links(row.get("projectLinks"))
    website = website or site
    twitter = twitter or handle
    if info:
        item["info"] = info
    if website:
        item["website"] = website
    if twitter:
        item["twitter"] = twitter
    return item


def _profile(html):
    """Use a short blurb, and a site or X account only when the description labels it as official."""
    if not isinstance(html, str) or not html.strip():
        return None, None, None
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    info = text or None
    website = _site_url(_labeled(html, r"Official\s+(?:Website|Site)|官网") or "")
    twitter = _x_url(_labeled(html, r"Official\s+(?:X|Twitter)|官推") or "")
    return info, website, twitter


def _structured_links(value):
    """Official projectLinks JSON. Blank or non-official values stay empty."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None, None
    if not isinstance(value, dict):
        return None, None
    website = twitter = None
    for key in ("mvpLink", "website", "officialWebsite", "siteLink", "webLink"):
        website = _site_url(value.get(key) or "")
        if website:
            break
    for key in ("xLink", "twitterLink", "twitterUrl", "xUrl"):
        twitter = _x_url(value.get(key) or "")
        if twitter:
            break
    return website, twitter


def _labeled(html, labels):
    found = []
    pattern = rf'(?:{labels})\s*[:：]\s*(?:<a\b[^>]*href="(https?://[^"?#\s]+)"|(https?://\S+))'
    for match in re.finditer(pattern, html, re.I):
        raw = next(group for group in match.groups() if group)
        cleaned = raw.rstrip(").,;")
        host = (urlsplit(cleaned).hostname or "").lower()
        if host and cleaned not in found:
            found.append(cleaned)
    return found[0] if len(found) == 1 else None


_RESERVED_HANDLES = {"intent", "share", "home", "search", "explore", "i", "hashtag", "compose"}
_SITE_HOSTS = {"x.com", "twitter.com", "github.com", "youtube.com", "youtu.be", "loom.com", "t.me", "discord.com", "discord.gg"}


def _site_url(value):
    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        return None
    cleaned = value.strip().rstrip(").,;")
    parts = urlsplit(cleaned)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.scheme not in {"http", "https"} or "." not in host or parts.username or host in _SITE_HOSTS:
        return None
    return cleaned.split("#", 1)[0]


def _x_url(value):
    if not isinstance(value, str) or not value.strip():
        return None
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.scheme != "https" or host not in {"x.com", "twitter.com"} or parts.username:
        return None
    handle = parts.path.strip("/").split("/")[0]
    if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) and handle.lower() not in _RESERVED_HANDLES:
        return f"https://x.com/{handle}"
    return None


def get_submissions(event_id, timeout):
    page, limit = 1, 12
    projects = {}
    total = None
    while total is None or (page - 1) * limit < total:
        data = graphql(PROJECTS, {
            "filter": {"hackathonId": event_id, "orderBy": [{"updatedAt": "desc"}]},
            "page": page, "limit": limit,
        }, timeout).get("projects")
        if (not isinstance(data, dict) or type(data.get("total")) is not int or
                data["total"] < 0 or not isinstance(data.get("data"), list)):
            raise ValueError("HackQuest 未返回可验证的公开展厅及总数")
        if total is None:
            total = data["total"]
        if data["total"] != total or len(data["data"]) != min(limit, total - (page - 1) * limit):
            raise ValueError("HackQuest 公开展厅在分页期间变化，等待下轮重读")
        for row in data["data"]:
            value = project(row)
            projects[value["id"]] = value
        page += 1
    if len(projects) != total:
        raise ValueError("HackQuest 项目去重后与公开总数不一致，等待下轮重读")
    return list(projects.values()), total


def get_winners(event_id, timeout):
    groups = graphql(REWARDS, {"hackathonId": event_id}, timeout).get("findHackathonReward")
    if not isinstance(groups, list) or any(
        not isinstance(group, dict) or type(group.get("announce")) is not bool
        for group in groups
    ):
        raise ValueError("HackQuest 未返回可验证的赛道公布状态")
    announced = [group for group in groups if group["announce"]]
    winners = []
    for group in announced:
        rows = group.get("projects")
        if not isinstance(rows, list):
            raise ValueError("HackQuest 已公布赛道缺少获奖项目数据")
        for row in rows:
            if not isinstance(row, dict) or "winner" not in row:
                raise ValueError("HackQuest 获奖记录格式改变")
            records = row["winner"]
            if records is None:
                continue
            if not isinstance(records, list):
                raise ValueError("HackQuest 获奖记录格式改变")
            for winner in records:
                if not isinstance(winner, dict) or winner.get("rewardId") is None:
                    raise ValueError("HackQuest 获奖记录缺少赛道 ID")
                if str(winner["rewardId"]) != str(group.get("id")):
                    continue
                rank = winner.get("place")
                winners.append({**project(row), "category": group.get("name") or group.get("rewardName"),
                                "rank": str(rank) if rank is not None else None})
    return winners, len(announced), len(groups)


def fetch_hackquest(url, html, timeout=15):
    result = parse_hackquest(url, html)
    event_id = result["platform_event_id"]
    try:
        result["submissions"], total = get_submissions(event_id, timeout)
        result["public_gallery_count"] = total
        if total:
            result["submission_status"] = "published"
        elif result["platform_project_count"] == 0:
            result["submission_status"] = "empty"
    except (OSError, ValueError) as exc:
        result.update(submission_status="error", submission_error=str(exc))
    try:
        result["winners"], published, total = get_winners(event_id, timeout)
        result.update(winner_tracks_published=published, winner_tracks_total=total)
        if published:
            if published < total:
                result["winner_status"] = "partial"
            else:
                result["winner_status"] = "published" if result["winners"] else "empty"
        elif total:
            result["winner_status"] = "not_published"
    except (OSError, ValueError) as exc:
        result.update(winner_status="error", winner_error=str(exc))
    return result
