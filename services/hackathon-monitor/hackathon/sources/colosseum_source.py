"""Colosseum's public competition directory, exports, and awarded entries."""

from datetime import datetime
from html import unescape
from io import BytesIO
import json
import re
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


HOME = "https://colosseum.com"
DISCOVERY = HOME + "/hackathon"
API = "https://api.colosseum.com/api/projects"
DIRECTORIES = API + "/directories"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PHASES = {1: "registration", 2: "submissions_open", 3: "judging", 4: "completed"}
WEB_PHASES = {
    "upcoming": "scheduled", "scheduled": "scheduled", "registration": "registration",
    "register": "registration", "live": "active", "building": "submissions_open",
    "submissions_open": "submissions_open", "judging": "judging",
    "complete": "completed", "completed": "completed", "winners_announced": "completed",
}
TRACKS = {
    "SOL": r"solana",
    "BSC": r"(?:bnb smart chain|bnb chain|bsc)",
}
PAGE_SIZE = 50


def _get(url, timeout, accept):
    headers = {"User-Agent": "SolBscHackathonMonitor/2.0", "Accept": accept}
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError("Colosseum 响应超过 8 MB")
    return data


def _text(url, timeout):
    return _get(url, timeout, "application/json,text/html,*/*;q=0.5").decode("utf-8")


def _local_url(value):
    url = urljoin(HOME, value or "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"colosseum.com", "www.colosseum.com"}:
        raise ValueError("Colosseum 赛事链接无效")
    return url


def _hackathon_list(fetch, timeout):
    data = json.loads(fetch(DIRECTORIES, timeout))
    rows = data.get("hackathons") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), int)
        or not isinstance(row.get("name"), str) or not isinstance(row.get("landingPageUrl"), str)
        for row in rows
    ):
        raise ValueError("Colosseum 公开赛事目录格式变化")
    return rows


def _web_event(html):
    match = re.search(r"currentEvent:\{([^{}]{1,4000})", html)
    if not match:
        return {}
    values = dict(re.findall(r'(\w+):("(?:[^"\\]|\\.)*")', match.group(1)))
    return {key: json.loads(value) for key, value in values.items()}


def _track_chains(html):
    headings = re.findall(r"<(?:h[1-4]|title)\b[^>]*>(.*?)</(?:h[1-4]|title)>", html, flags=re.I | re.S)
    headings = [" ".join(unescape(re.sub(r"<[^>]+>", " ", name)).split()) for name in headings]
    # Example official heading: "Solana Ecosystem" in Crypto World's Fair tracks.
    return [
        chain for chain, pattern in TRACKS.items()
        if any(re.search(rf"\b(?:{pattern})\b", name, re.I)
               and re.search(r"\b(?:ecosystem|track|hackathon)\b", name, re.I) for name in headings)
    ]


def discover_colosseum(timeout=15):
    """Discover active events with a verified SOL or BSC track."""
    active = {}
    for row in _hackathon_list(_text, timeout):
        stage = PHASES.get(row.get("phase"))
        if stage and stage != "completed":
            active[_local_url(row["landingPageUrl"])] = (row["name"], stage)
    # A registration event may appear on the public site before its directory is enabled.
    current = _web_event(_text(DISCOVERY, timeout))
    stage = WEB_PHASES.get(current.get("phase"))
    if current.get("eventType") == "hackathon" and stage and stage != "completed":
        active.setdefault(_local_url(current.get("landingPageUrl")), (current.get("name"), stage))
    out = []
    for url, (name, stage) in active.items():
        chains = _track_chains(_text(url, timeout))
        if chains and name:
            out.append({"name": name, "url": url, "kind": "colosseum",
                        "chain": ", ".join(chains), "event_status": stage})
    return out


def _project_page(hackathon_id, fetch, timeout, offset=0, winners=False):
    params = {"hackathonIds[]": hackathon_id, "includeEternal": "false",
              "sort": "NAME", "direction": "asc", "limit": PAGE_SIZE, "offset": offset,
              "showWinnersOnly": str(winners).lower()}
    data = json.loads(fetch(f"{API}?{urlencode(params)}", timeout))
    if (not isinstance(data, dict) or not isinstance(data.get("projects"), list)
            or type(data.get("totalCount")) is not int or data["totalCount"] < 0
            or type(data.get("hasMore")) is not bool or data.get("offset") != offset):
        raise ValueError("Colosseum 作品目录分页格式变化")
    return data


def _api_projects(hackathon_id, page, fetch, timeout, winners=False):
    total = page["totalCount"]
    projects = []
    identities = set()
    while True:
        offset = page["offset"]
        for row in page["projects"]:
            if (not isinstance(row, dict) or row.get("hackathonId") != hackathon_id
                    or not isinstance(row.get("slug"), str) or not row["slug"]
                    or row["slug"] in identities or not isinstance(row.get("name"), str)
                    or not row["name"].strip()):
                raise ValueError("Colosseum 作品分页有重复或缺少项目字段")
            identities.add(row["slug"])
            projects.append(row)
        if not page["hasMore"]:
            break
        if len(projects) != offset + PAGE_SIZE or len(projects) >= total:
            raise ValueError("Colosseum 作品分页返回不完整")
        page = _project_page(hackathon_id, fetch, timeout, offset + PAGE_SIZE, winners)
        if total != page["totalCount"]:
            raise ValueError("Colosseum 作品总数在分页期间变化")
    if len(projects) != total:
        raise ValueError("Colosseum 作品数量和公开总数不符")
    return projects


def _xml(archive, member):
    data = archive.getinfo(member)
    if data.file_size > 24_000_000:
        raise ValueError("Colosseum 导出工作表超过 24 MB")
    content = archive.read(data)
    if b"<!DOCTYPE" in content.upper():
        raise ValueError("Colosseum 导出工作表 XML 格式异常")
    return ET.fromstring(content)


def _export_projects(hackathon_id, total, timeout):
    export = _get(f"{API}/export?hackathonId={hackathon_id}", timeout, EXCEL)
    with ZipFile(BytesIO(export)) as book:
        strings = ["".join(node.itertext()) for node in _xml(book, "xl/sharedStrings.xml")]
        sheet = _xml(book, "xl/worksheets/sheet1.xml")
        links = {link.get("Id"): link.get("Target")
                 for link in _xml(book, "xl/worksheets/_rels/sheet1.xml.rels")}
        relationship = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        references = {cell.get("ref"): links.get(cell.get(relationship))
                      for cell in sheet.findall(".//{*}hyperlink")}

    def cells(row):
        out = {}
        for cell in row.findall("{*}c"):
            address = cell.get("r", "")
            column = re.sub(r"\d+$", "", address)
            value = cell.findtext("{*}v") or ""
            if cell.get("t") == "s":
                value = strings[int(value)]
            elif cell.get("t") == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
            out[column] = (value.strip(), address)
        return out

    columns = None
    projects = []
    ids = set()
    for row in sheet.findall(".//{*}row"):
        fields = cells(row)
        if columns is None:
            if "Project" in {value for value, _ in fields.values()}:
                columns = {value: column for column, (value, _) in fields.items()}
            continue
        name, address = fields.get(columns["Project"], ("", ""))
        if not name:
            continue
        url = references.get(address)
        if not isinstance(url, str):
            raise ValueError("Colosseum 导出作品缺少公开链接")
        parsed = urlsplit(_local_url(url))
        match = re.fullmatch(r"/arena/projects/([^/]+)/?", parsed.path)
        if not match or match[1] in ids:
            raise ValueError("Colosseum 导出作品链接重复或格式变化")
        ids.add(match[1])
        category = fields.get(columns.get("Category"), ("", ""))[0]
        chains = fields.get(columns.get("Chains"), ("", ""))[0]
        projects.append({"id": match[1], "name": name, "url": url,
                         "category": category or None, "chain": chains or None})
    if columns is None or len(projects) != total:
        raise ValueError("Colosseum 导出作品总数和公开目录不符")
    return projects


def _api_item(row):
    return {"id": quote(row["slug"], safe=""), "name": row["name"],
            "url": f"{HOME}/arena/projects/{quote(row['slug'], safe='')}",
            "category": row.get("category")}


def _schedule(data):
    result = []
    for key, kind, label in (
        ("startDate", "starts", "Colosseum 赛事开始"),
        ("projectSubmissionStartDate", "submission_open", "Colosseum 提交开放"),
        ("projectSubmissionEndDate", "submission_close", "Colosseum 提交截止"),
        ("endDate", "ends", "Colosseum 赛事结束"),
    ):
        value = data.get(key)
        if not isinstance(value, str):
            continue
        try:
            when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is not None:
            result.append({"kind": kind, "label": label, "time": when.isoformat(),
                           "precision": "datetime"})
    return result


def fetch_colosseum(url, fetch, timeout=15):
    """Read all public submissions and awards for a known Colosseum competition."""
    url = _local_url(url)
    pages = _hackathon_list(fetch, timeout)
    parsed = urlsplit(url)
    id_value = parse_qs(parsed.query).get("hackathonId", [None])[0]
    event = next((row for row in pages if str(row["id"]) == id_value or
                  urlsplit(row["landingPageUrl"]).path.rstrip("/") == parsed.path.rstrip("/")), None)
    if event is None:
        current = _web_event(fetch(url, timeout))
        if (not current.get("landingPageUrl") or
                urlsplit(_local_url(current["landingPageUrl"])).path.rstrip("/") != parsed.path.rstrip("/")):
            raise ValueError("Colosseum 未确认此赛事的公开目录")
        return {"name": current.get("name"), "event_status": WEB_PHASES.get(current.get("phase")),
                "submission_status": "unverified", "winner_status": "unverified",
                "submissions": [], "winners": [], "schedule": [], "links": []}
    hackathon_id = event["id"]
    phase = event.get("phase")
    result = {"name": event["name"], "platform_event_id": str(hackathon_id), "links": [],
              "event_status": PHASES.get(phase), "schedule": [],
              "submission_status": "unverified", "winner_status": "unverified",
              "submissions": [], "winners": []}
    try:
        page = _project_page(hackathon_id, fetch, timeout)
        metadata = next((row for row in page.get("hackathons", []) if row.get("id") == hackathon_id), {})
        phase = metadata.get("phase", phase)
        result["event_status"] = PHASES.get(phase)
        result["schedule"] = _schedule(metadata)
        result["public_gallery_count"] = total = page["totalCount"]
        if total:
            try:
                items = _export_projects(hackathon_id, total, timeout)
            except (OSError, ValueError, BadZipFile, ET.ParseError, KeyError, IndexError) as error:
                items = [_api_item(row) for row in _api_projects(hackathon_id, page, fetch, timeout)]
                result["chain_metadata_error"] = str(error)
            result["submissions"], result["submission_status"] = items, "published"
        elif metadata.get("isProjectDirectoryEnabled") is True:
            result["submission_status"] = "empty"
        elif metadata.get("isProjectDirectoryEnabled") is False:
            result["submission_status"] = "not_published"
    except (OSError, ValueError, TypeError, KeyError) as error:
        result.update(submission_status="error", submission_error=str(error))
    try:
        page = _project_page(hackathon_id, fetch, timeout, winners=True)
        entries = _api_projects(hackathon_id, page, fetch, timeout, winners=True)
        chains = {item["id"]: item.get("chain") for item in result["submissions"]}
        for entry in entries:
            prize = entry.get("prize")
            if not isinstance(prize, dict) or not isinstance(prize.get("name"), str):
                raise ValueError("Colosseum 获奖条目没有可核实的奖名")
            item = _api_item(entry)
            item.update(category=prize.get("track") or prize.get("name"),
                        rank=str(prize["placement"]) if prize.get("placement") is not None else prize["name"],
                        chain=chains.get(item["id"]))
            result["winners"].append(item)
        if phase == 4:
            result["winner_status"] = "published" if entries else "empty"
        else:
            result["winner_status"] = "partial" if entries else "not_published"
    except (OSError, ValueError, TypeError, KeyError) as error:
        result.update(winner_status="error", winner_error=str(error), winners=[])
    return result
