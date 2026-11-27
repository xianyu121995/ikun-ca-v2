"""Read public contest data from the Solana Foundation hackathon site."""

from datetime import datetime
import json
import re
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


ORIGIN = "https://hackathons.solana.com"
DIRECTORY = ORIGIN + "/hackathons"
FOLLOWED_STATES = {"scheduled", "active", "live", "launched", "open", "judging"}
BEFORE_OPEN = {"scheduled", "funding"}
SLUG = re.compile(r"[a-zA-Z0-9-]+")
EVENT_PATH = re.compile(r"/hackathons/([a-zA-Z0-9-]+)/?")
FLIGHT = re.compile(r"self\.__next_f\.push\(")
DECODER = json.JSONDecoder()


def flight(html):
    parts = []
    for marker in FLIGHT.finditer(html):
        try:
            chunk, _ = DECODER.raw_decode(html, marker.end())
        except ValueError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and chunk[0] == 1 and isinstance(chunk[1], str):
            parts.append(chunk[1])
    if not parts:
        raise ValueError("Solana 页面未提供可识别的公开数据")
    return "".join(parts)


def embedded(stream, key):
    for marker in re.finditer(r'"' + re.escape(key) + r'"\s*:\s*', stream):
        try:
            value, _ = DECODER.raw_decode(stream, marker.end())
        except ValueError:
            continue
        return value
    return None


def event_props(stream, slug):
    for marker in re.finditer(r'\{\s*"initialDisplayStatus"\s*:', stream):
        try:
            props, _ = DECODER.raw_decode(stream, marker.start())
        except ValueError:
            continue
        event = props.get("hackathon")
        if isinstance(event, dict) and event.get("slug") == slug and event.get("id") and event.get("title"):
            return props
    raise ValueError("Solana 页面没有与链接相符的公开赛事详情")


def exact_time(value):
    if not isinstance(value, str):
        return None
    raw = value.removeprefix("$D")
    if "T" not in raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.isoformat() if stamp.tzinfo else None


def parse_directory(html):
    stream = flight(html)
    events = embedded(stream, "initialHackathons")
    display_statuses = embedded(stream, "initialStatuses")
    if not isinstance(events, list):
        raise ValueError("Solana 官方赛事目录未返回可验证的列表")
    display_statuses = display_statuses if isinstance(display_statuses, dict) else {}
    found = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Solana 赛事目录的条目格式改变")
        slug, name = event.get("slug"), event.get("title")
        event_id = event.get("id")
        status = display_statuses.get(event_id, event.get("status"))
        if status not in FOLLOWED_STATES and event.get("status") not in FOLLOWED_STATES:
            continue
        if (event.get("hidden") or not isinstance(slug, str) or not SLUG.fullmatch(slug)
                or not isinstance(name, str) or not name.strip() or not isinstance(event_id, str)):
            continue
        found.append({
            "name": name.strip(), "url": f"{DIRECTORY}/{slug}", "kind": "solana",
            "chain": "SOL", "event_status": status, "platform_event_id": event_id,
            "start_at": exact_time(event.get("launch_date")),
        })
    return found


def discover_solana(timeout=15):
    request = Request(DIRECTORY, headers={"User-Agent": "Mozilla/5.0 (compatible; HackathonMonitor/1.0)"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(6_000_001)
        if len(body) > 6_000_000:
            raise ValueError("Solana 赛事目录响应超过 6 MB")
    return parse_directory(body.decode("utf-8", errors="replace"))


def project_item(row, event, bounty_names):
    if not isinstance(row, dict) or row.get("hackathon_id") != event["id"]:
        raise ValueError("Solana 公开作品的赛事 ID 不匹配")
    identity, name = row.get("id"), row.get("project_name")
    if not isinstance(identity, str) or not identity or not isinstance(name, str) or not name.strip():
        raise ValueError("Solana 公开作品缺少 ID 或名称")
    item = {
        "id": identity, "name": name.strip(), "chain": "SOL",
        "url": f"{DIRECTORY}/{event['slug']}/projects/{quote(identity, safe='')}",
    }
    categories = list(dict.fromkeys(
        bounty_names[bounty] for bounty in row.get("bounty_ids") or [] if bounty in bounty_names
    ))
    if categories:
        item["category"] = " · ".join(categories)
    submitted = exact_time(row.get("submitted_at"))
    if submitted:
        item["submitted_at"] = submitted
    return item


def official_winners(props, event, bounty_names, html, status):
    # Count named projects published in the Results section, not unsigned assignments.
    if not re.search(r">\s*Winning projects\s*<", html):
        return [], None
    published = props.get("winners")
    if not isinstance(published, list):
        raise ValueError("Solana 结果区没有公开获奖名单")
    projects = {row["id"]: project_item(row, event, bounty_names) for row in published}
    awards = []
    prizes = event.get("main_track_prizes") or []
    for entry in props.get("mainTrackWinners") or []:
        identity, place = entry.get("submission_id"), entry.get("place")
        if identity not in projects:
            continue
        # place numbers position the records in the configured prize list.
        # Separate positions can intentionally show the same public ranking.
        rank = prizes[place - 1].get("label") if type(place) is int and 1 <= place <= len(prizes) else None
        awards.append({**projects[identity], "category": "Main track", "rank": rank})
    for bounty in event.get("bounties") or []:
        category = bounty.get("track_name")
        for award in bounty.get("winners") or []:
            identity = award.get("submission_id")
            if identity in projects and isinstance(category, str) and category.strip():
                awards.append({**projects[identity], "category": category.strip(), "rank": None})
    recognized = {award["id"] for award in awards}
    if len(recognized) != len(projects):
        awards.extend({**item, "category": None, "rank": None}
                      for key, item in projects.items() if key not in recognized)
        return awards, "partial"
    if status != "completed":
        return awards, "partial" if awards else None
    return awards, "published" if awards else "empty"


def read_project_rows(props, event, bounty_names, status, showcase, fetch, timeout):
    rows = props.get("publicSubmissions")
    total = props.get("submissionCount")
    if rows is None and status in BEFORE_OPEN:
        return [], "not_published"
    if rows is None:
        listing = embedded(flight(fetch(showcase, timeout)), "projects")
        if not isinstance(listing, list) or not all(isinstance(row, dict) for row in listing):
            raise ValueError("Solana 官方作品展厅未返回可验证的公开名单")
        rows = [row for row in listing if row.get("hackathon_id") == event["id"]]
    if not isinstance(rows, list):
        raise ValueError("Solana 公开作品的列表格式改变")
    projects = {}
    for row in rows:
        item = project_item(row, event, bounty_names)
        projects[item["id"]] = item
    if projects:
        return list(projects.values()), "published"
    return [], "empty" if total == 0 else "unverified"


def fetch_solana(url, fetch, timeout=15):
    parsed = urlsplit(url)
    match = EVENT_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "hackathons.solana.com" or not match:
        raise ValueError("Solana 来源必须是 Solana Foundation 官方赛事详情链接")
    official_url = f"{DIRECTORY}/{match[1]}"
    html = fetch(official_url, timeout)
    props = event_props(flight(html), match[1])
    event = props["hackathon"]
    status = props.get("initialDisplayStatus") or event.get("status")
    showcase = ORIGIN + "/showcase?" + urlencode({"hackathon": event["id"]})
    schedule = []
    for key, kind, label in (
        ("launch_date", "starts", "赛事开始"),
        ("submission_deadline", "submission_close", "作品提交截止"),
        ("judging_deadline", "judging_end", "评审截止"),
    ):
        stamp = exact_time(event.get(key))
        if stamp:
            schedule.append({"kind": kind, "label": label, "time": stamp, "precision": "datetime"})

    count = props.get("submissionCount")
    bounty_names = {
        bounty["id"]: bounty["track_name"] for bounty in event.get("bounties") or []
        if isinstance(bounty, dict) and isinstance(bounty.get("id"), str)
        and isinstance(bounty.get("track_name"), str) and bounty["track_name"].strip()
    }
    result = {
        "name": event["title"].strip(), "chain": "SOL", "platform_event_id": event["id"],
        "event_status": status, "schedule": schedule, "links": [showcase],
        "platform_project_count": count if type(count) is int else None,
        "submission_status": "unverified", "winner_status": "unverified",
        "submissions": [], "winners": [],
    }
    try:
        projects, publication = read_project_rows(props, event, bounty_names, status, showcase, fetch, timeout)
        result.update(submissions=projects, submission_status=publication)
        if publication in {"published", "empty"}:
            result["public_gallery_count"] = len(projects)
    except (OSError, ValueError, TypeError, KeyError) as error:
        result.update(submission_status="error", submission_error=str(error))
    try:
        winners, publication = official_winners(props, event, bounty_names, html, status)
        if publication is None:
            publication = "not_published" if status in BEFORE_OPEN or "winners" in props and props["winners"] is None else "unverified"
        result.update(winners=winners, winner_status=publication)
    except (ValueError, TypeError, KeyError) as error:
        result.update(winner_status="error", winner_error=str(error))
    return result

