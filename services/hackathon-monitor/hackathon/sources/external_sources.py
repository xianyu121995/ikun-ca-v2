"""Public Superteam Earn hackathon and side-track listings on Solana."""

from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


SUPERTEAM = "https://superteam.fun"
DIRECTORY = SUPERTEAM + "/earn"
LIVE_DIRECTORY = SUPERTEAM + "/api/listings/live"
HOSTS = {"superteam.fun", "www.superteam.fun", "earn.superteam.fun"}
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
ROUTE = re.compile(rf"/(?:earn/)?(hackathon|listing)/({SLUG})/?$")
CAMPAIGN_LINK = re.compile(rf'href=["\x27](?:https://superteam\.fun)?/earn/hackathon/({SLUG})/?(?:[?"\x27#])')
NEXT_DATA = re.compile(r'<script[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def _download(url, timeout):
    request = Request(url, headers={"User-Agent": "BscHackathonMonitor/1.0"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError("Superteam Earn 响应超过 6 MB")
        return data.decode("utf-8")


def _api(path, fetch, timeout, expected_type):
    url = SUPERTEAM + path
    data = json.loads(fetch(url, timeout))
    if not isinstance(data, expected_type):
        raise ValueError(f"Superteam Earn 响应格式变化：{url}")
    return data


def _route(url):
    parts = urlsplit(url)
    match = ROUTE.fullmatch(parts.path)
    if parts.scheme != "https" or parts.hostname not in HOSTS or not match:
        raise ValueError("链接不是 Superteam Earn 公开赛事或赛道页")
    return match.groups()


def recognize_external(url):
    try:
        _route(url)
    except ValueError:
        return False
    return True


def _page(route, slug):
    return f"{SUPERTEAM}/earn/{route}/{slug}"


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


def _schedule(kind, label, value):
    return [{"kind": kind, "label": label, "time": value}] if _time(value) else []


def _stage(deadline, announced):
    if announced:
        return "completed"
    close = _time(deadline)
    if close is None:
        return "unknown"
    return "active" if close > datetime.now(timezone.utc) else "awaiting_results"


def discover_external_catalog(timeout=15, fetch=_download):
    document = fetch(DIRECTORY, timeout)
    if "Superteam Earn" not in document:
        raise ValueError("Superteam Earn 首页响应不含网站标识")
    slugs = dict.fromkeys(CAMPAIGN_LINK.findall(document))
    return [{"name": "Superteam Earn · " + slug.replace("-", " ").title(), "chain": "SOL",
             "url": _page("hackathon", slug), "kind": "external"} for slug in slugs]


def discover_external_live(timeout=15, fetch=_download):
    since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    query = urlencode({"take": 50, "type": "hackathon", "deadline": since})
    listings = _api("/api/listings/live?" + query, fetch, timeout, list)
    return [{"name": str(row["title"]), "chain": "SOL",
             "url": _page("listing", row["slug"]), "kind": "external",
             "event_status": _stage(row.get("deadline"), False)}
            for row in listings if isinstance(row, dict) and row.get("type") == "hackathon"
            and row.get("isWinnersAnnounced") is False and row.get("title")
            and re.fullmatch(SLUG, str(row.get("slug") or ""))]


def discover_external(timeout=15):
    return discover_external_catalog(timeout) + discover_external_live(timeout)


def _campaign(slug, fetch, timeout):
    url = _page("hackathon", slug)
    script = NEXT_DATA.search(fetch(url, timeout))
    if not script:
        raise ValueError("Superteam Earn 赛事页无法读取公开赛程")
    page = json.loads(script[1])["props"]["pageProps"]["hackathon"]
    if not isinstance(page, dict) or page.get("slug") != slug or not page.get("name"):
        raise ValueError("Superteam Earn 赛事资料与请求不符")
    schedule = (_schedule("starts", "Campaign Start", page.get("startDate"))
                + _schedule("submission_close", "Campaign Submission Deadline", page.get("deadline")))
    tracks = _api(f"/api/hackathon/{slug}", fetch, timeout, list)
    links = [_page("listing", row["slug"]) for row in tracks if isinstance(row, dict)
             and re.fullmatch(SLUG, str(row.get("slug") or ""))]
    return {
        "name": "Superteam Earn · " + page["name"] + " 赞助赛道",
        "chain": "SOL", "event_status": "unknown",
        "submission_status": "unverified", "submissions": [],
        "winner_status": "unverified", "winners": [],
        "schedule": schedule, "links": links,
        "scope_note": "赛道各自发布提交及获奖名单，详见对应赛道；此页只列出赛道。",
    }


def _public_link(value):
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.strip()
    if "://" not in url:
        url = "https://" + url.removeprefix("//")
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme in {"https", "http"} and parts.hostname and not parts.username and not parts.password:
        return url
    return None


def _entry(row, published_at, listing_url):
    user = row.get("user") or {}
    username = user.get("username")
    visible_name = "@" + username if username else " ".join(
        str(user[field]) for field in ("firstName", "lastName") if user.get(field))
    if not visible_name:
        visible_name = "未公开提交账号"
    link = _public_link(row.get("link"))
    item = {
        "id": str(row["id"]), "name": visible_name + "（项目名未公开）",
        "url": link or listing_url, "published_at": published_at,
    }
    host = (urlsplit(link).hostname or "").lower() if link else ""
    if link and host and "superteam" not in host and not host.endswith(("x.com", "twitter.com")):
        item["website"] = link
    return item


def _published_listing(result, detail, fetch, timeout):
    listing_url = _page("listing", detail["slug"])
    published_at = detail.get("winnersAnnouncedAt")
    result["published_at"] = published_at
    by_id = {}
    try:
        payload = _api("/api/listings/submissions/" + detail["slug"], fetch, timeout, dict)
        rows = payload["submission"]
        if not isinstance(rows, list):
            raise ValueError("提交名单格式变化")
        by_id = {str(row["id"]): _entry(row, published_at, listing_url) for row in rows}
        result.update(submissions=list(by_id.values()),
                      submission_status="published" if rows else "empty")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result.update(submission_status="error", submission_error=str(error))

    try:
        public_winners = _api(f"/api/listings/{detail['id']}/winners", fetch, timeout, list)
        winners = []
        for row in public_winners:
            entry = by_id.get(str(row["id"])) or _entry(row, published_at, listing_url)
            position = row.get("winnerPosition")
            rank = "Bonus" if position == 99 else f"第 {position} 名" if position else None
            winners.append({**entry, "category": detail["title"], "rank": rank})
        result.update(winners=winners, winner_status="published" if winners else "empty")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result.update(winner_status="error", winner_error=str(error))


def fetch_external(url, fetch, timeout=15):
    route, slug = _route(url)
    if route == "hackathon":
        return _campaign(slug, fetch, timeout)
    detail = _api("/api/listings/details/" + slug, fetch, timeout, dict)
    if (detail.get("type") != "hackathon" or detail.get("isPrivate") or detail.get("isPublished") is not True
            or detail.get("slug") != slug or not detail.get("id") or not detail.get("title")):
        raise ValueError("该页面不是已公开的 Superteam Earn 黑客松赛道")
    announced = detail.get("isWinnersAnnounced")
    initial = "not_published" if announced is False else "unverified"
    listing_url = _page("listing", slug)
    schedule = (_schedule("submission_close", "Submission Deadline", detail.get("deadline"))
                + _schedule("results_expected", "Winner Announcement By", detail.get("commitmentDate")))
    result = {
        "name": detail["title"], "chain": "SOL", "event_status": _stage(detail.get("deadline"), announced),
        "submission_status": initial, "submissions": [], "winner_status": initial, "winners": [],
        "schedule": schedule, "links": [],
        "event_website": listing_url,
        "scope_note": "Superteam Earn 公布获奖后开放提交记录，数据给出公开提交链接及账号。",
    }
    parent = detail.get("Hackathon") or {}
    parent_slug = str(parent.get("slug") or "")
    if re.fullmatch(SLUG, parent_slug):
        result["parent_event_url"] = _page("hackathon", parent_slug)
        if parent_slug == "crypto-worlds-fair":
            result["organizer_event_url"] = "https://colosseum.com/worldsfair"
    if announced is True:
        _published_listing(result, detail, fetch, timeout)
    return result
