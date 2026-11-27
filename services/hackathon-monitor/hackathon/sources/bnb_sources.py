"""Read public BNB Chain and Luma data embedded in their event pages."""

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit


_BNB_HOSTS = {"bnbchain.org", "www.bnbchain.org"}
_LUMA_HOSTS = {"luma.com", "lu.ma", "www.luma.com"}
_HACKATHON = re.compile(r"\bhackathons?\b|\bbuildathons?\b|\bbnb hack\b|\bdemo (?:night|day)\b", re.I)
_RESULT = re.compile(r"\bwinners?\b|\bresults?\b|\brecap\b|\bcongratulat", re.I)


def _clean(value):
    return " ".join(value.replace("\u200b", "").split()) if isinstance(value, str) else ""


class _Page(HTMLParser):
    """Collect Next.js state, useful text blocks, and their readable links."""

    def __init__(self, html):
        super().__init__()
        self.props = {}
        self.schemas = []
        self.links = []
        self.blocks = []
        self._script = None
        self._parts = []
        self._style = False
        self._anchor = None
        self._blocks = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self._script = (
                "next" if attrs.get("id") == "__NEXT_DATA__"
                else "ld" if attrs.get("type") == "application/ld+json"
                else "skip"
            )
            self._parts = []
            return
        if tag == "style":
            self._style = True
        if self._script or self._style:
            return
        if tag == "a" and attrs.get("href"):
            self._anchor = (attrs["href"], [], [])
        if tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._blocks.append((tag, [], []))

    def handle_endtag(self, tag):
        if tag == "script":
            if self._script in {"next", "ld"}:
                try:
                    data = json.loads("".join(self._parts))
                except ValueError:
                    data = {}
                if isinstance(data, dict):
                    if self._script == "next":
                        self.props = data.get("props", {}).get("pageProps", {})
                    else:
                        self.schemas.append(data)
            self._script = None
            return
        if tag == "style":
            self._style = False
            return
        if self._script or self._style:
            return
        if tag == "a" and self._anchor:
            href, parts, paragraphs = self._anchor
            label = _clean("".join(parts))
            self.links.append((href, label, paragraphs))
            for _, _, links in self._blocks:
                links.append((href, label))
            self._anchor = None
        if self._blocks and tag == self._blocks[-1][0]:
            _, parts, links = self._blocks.pop()
            value = _clean("".join(parts))
            if value:
                self.blocks.append((tag, value, links))
                if tag == "p" and self._anchor:
                    self._anchor[2].append(value)

    def handle_data(self, data):
        if self._script:
            if self._script != "skip":
                self._parts.append(data)
            return
        if self._style:
            return
        if self._anchor:
            self._anchor[1].append(data)
        for _, parts, _ in self._blocks:
            parts.append(data)


def _cms(page):
    return page.props.get("initialState", {}).get("cms", {})


def _luma(page):
    return page.props.get("initialData", {}).get("data", {})


def _result_links(page, base):
    urls = set()
    for raw, label, _ in page.links:
        link = urlsplit(urljoin(base, raw))
        if link.scheme not in {"http", "https"} or not link.hostname:
            continue
        host = link.hostname
        path = link.path.rstrip("/")
        if (
            (host in _LUMA_HOSTS and re.fullmatch(r"/[a-z0-9-]+", path, re.I)
             and re.search(r"hackathon|demo night|developer track|startup track|pitch", label, re.I))
            or (host in {"dorahacks.io", "www.dorahacks.io"} and re.fullmatch(r"/hackathon/[^/]+(?:/[^/]+)?", path))
            or (host in {"hackquest.io", "www.hackquest.io"} and re.fullmatch(r"/hackathons/[^/]+", path))
            or (host in _BNB_HOSTS and (
                re.fullmatch(r"/en/hackathons/[^/]+", path)
                or (path.startswith("/en/blog/") and (
                    _HACKATHON.search(label)
                    or re.search(r"(?:winners?|results?).*(?:hack|buildathon)|(?:hack|buildathon).*(?:winners?|results?)", path, re.I)
                ))
            ))
        ):
            if path != urlsplit(base).path.rstrip("/") or host != urlsplit(base).hostname:
                urls.add(urlunsplit(("https", host, path, "", "")))
    return sorted(urls)


def discover_bnb(url, html):
    """Return identifiable event and results pages from supported public indexes."""
    page = _Page(html)
    location = urlsplit(url)
    found = {}
    if location.hostname in _BNB_HOSTS and location.path.rstrip("/") == "/en/hackathons":
        programs = _cms(page).get("hackathonPrograms")
        if not isinstance(programs, list):
            raise ValueError("BNB hackathon directory data is missing")
        for item in programs:
            slug, title = item.get("slug"), _clean(item.get("title"))
            if isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]+", slug) and title:
                if re.search(r"hackvolution.*opbnb and bnb greenfield", title, re.I):
                    continue
                link = f"https://www.bnbchain.org/en/hackathons/{slug}"
                found[link] = {
                    "url": link, "name": title, "kind": "bnb-event",
                    "start_at": _date_time(item.get("start"), item.get("timezone")),
                    "end_at": _date_time(item.get("end"), item.get("timezone")),
                    "event_year": _year(item.get("start")),
                    "event_status": "archived" if _clean(item.get("status")).casefold() == "ended"
                                    else _clean(item.get("status")),
                    "chain": "BSC",
                }
    elif location.hostname in _BNB_HOSTS and location.path.startswith("/en/blog"):
        cards = [row for row in page.links if row[0].startswith("/en/blog/") and row[2]]
        if not cards:
            raise ValueError("BNB blog article cards are missing")
        for raw, label, paragraphs in cards:
            title = paragraphs[0]
            event_teaser = (
                len(paragraphs) > 1
                and re.search(r"^BNB [^:]{2,35}:.*\b(?:demo|pitch)\b", title, re.I)
                and _HACKATHON.search(paragraphs[1])
            )
            if _HACKATHON.search(title) or event_teaser:
                link = urljoin("https://www.bnbchain.org", raw).split("?", 1)[0].rstrip("/")
                dates = re.findall(r"(?<![0-9])(20[0-9]{2})[.]([0-9]{1,2})[.]([0-9]{1,2})(?=\s*[0-9]+ min read)", label)
                if dates:
                    year, month, day = map(int, dates[-1])
                    try:
                        article_date = datetime(year, month, day).date().isoformat()
                    except ValueError:
                        article_date = None
                else:
                    article_date = None
                years = set(re.findall(r"(?<![0-9])20[0-9]{2}(?![0-9])", " ".join(paragraphs[:2])))
                found[link] = {
                    "url": link, "name": title, "kind": "bnb-news",
                    "article_date": article_date,
                    "event_year": int(next(iter(years))) if len(years) == 1 else None,
                    "chain": "BSC", "is_results": bool(_RESULT.search(title)),
                }
    elif location.hostname in _LUMA_HOSTS:
        data = _luma(page)
        if not isinstance(data.get("calendar"), dict):
            raise ValueError("Luma calendar data is missing")
        for section in ("upcoming", "past"):
            entries = (data.get(section) or {}).get("entries", [])
            for entry in entries:
                _collect_luma_event(found, entry)
        for entry in data.get("featured_items", []):
            _collect_luma_event(found, entry)
    return list(found.values())


def _collect_luma_event(found, entry):
    event = entry.get("event", {})
    name, slug = _clean(event.get("name")), event.get("url")
    tags = " ".join(_clean(tag.get("name")) for tag in entry.get("tags", []) if isinstance(tag, dict))
    if not _HACKATHON.search(f"{name} {tags}") and "bnb local hack" not in tags.casefold():
        return
    if isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]+", slug, re.I) and name:
        link = f"https://luma.com/{slug}"
        found[link] = {
            "url": link, "name": name, "kind": "luma-event",
            "start_at": _date_time(event.get("start_at")),
            "end_at": _date_time(event.get("end_at")),
            "event_year": _year(event.get("start_at")), "chain": "BSC",
        }


def _year(value):
    return int(value[:4]) if isinstance(value, str) and re.match(r"20[0-9]{2}-", value) else None


def _date_time(value, timezone_label=None):
    if not isinstance(value, str) or len(value) <= 10:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        match = re.fullmatch(r"UTC\s*([+-])([0-9]{1,2})(?::([0-5][0-9]))?", timezone_label or "")
        if not match:
            return None
        sign, hours, minutes = match.groups()
        delta = timedelta(hours=int(hours), minutes=int(minutes or 0))
        try:
            stamp = stamp.replace(tzinfo=timezone(delta if sign == "+" else -delta))
        except ValueError:
            return None
    return stamp.isoformat()


def _add_schedule(rows, kind, label, raw, zone=None):
    date = _date_time(raw, zone)
    if date:
        rows.append({"kind": kind, "label": label, "time": date, "precision": "time"})
    elif raw:
        rows.append({"kind": kind, "label": f"{label}: {raw}", "precision": "text"})


def _winner_article(content):
    winners = []
    category = ""
    for tag, value, links in content.blocks:
        if tag in {"h1", "h2", "h3", "h4"}:
            category = value
        if tag not in {"li", "p"}:
            continue
        ranked = re.fullmatch(
            r"(\d+(?:st|nd|rd|th)\s+(?:place|prize)|winner|honou?rable mention)"
            r"\s*(?:\(([^)]*)\)\s*)?[:—–,]\s*(.{1,160})",
            value, re.I,
        )
        if ranked:
            rank, _, name = ranked.groups()
        elif tag == "li" and re.match(r"(?:Best Use of|Special Awards?)\b", category, re.I):
            if not (value.startswith("@") or (links and len(value) <= 80 and len(value.split()) <= 12)):
                continue
            rank, name = "", value
        else:
            continue
        url = next((link for link, label in links if label and label in name and link.startswith("https://")), "")
        winners.append({"name": name, "category": category, "rank": rank, "url": url})
    return winners


def parse_bnb(url, html):
    """Extract dates and actually named winners from a supported official page."""
    page = _Page(html)
    location = urlsplit(url)
    result = {"links": [], "schedule": [], "winners": [], "winner_status": "unknown"}
    schedule = result["schedule"]
    if location.hostname in _LUMA_HOSTS:
        event = _luma(page).get("event", {})
        if not event.get("name"):
            raise ValueError("Luma event data is missing")
        result["name"] = event["name"]
        result["links"] = _result_links(page, url)
        _add_schedule(schedule, "starts", "Event starts", event.get("start_at"))
        _add_schedule(schedule, "ends", "Event ends", event.get("end_at"))
        schema = next((row for row in page.schemas if row.get("@type") == "Event"), {})
        start = _date_time(schema.get("startDate"))
        end = _date_time(schema.get("endDate"))
        if start and end and start[:10] == end[:10]:
            date = datetime.fromisoformat(start)
            for tag, value, _ in page.blocks:
                if tag != "p":
                    continue
                line = re.fullmatch(r"([0-9]{1,2}):([0-9]{2})\s*[-–—]\s*(.+)", value)
                if not line:
                    continue
                hour, minute, label = line.groups()
                if re.match(r"(?:awards|prize ceremony)\b", label, re.I):
                    kind = "awards_ceremony"
                elif re.search(r"\b(?:demo|demos|pitch|pitches)\b", label, re.I):
                    kind = "demo"
                else:
                    continue
                if int(hour) < 24 and int(minute) < 60:
                    time = date.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                    _add_schedule(schedule, kind, label, time.isoformat())
        return result

    if location.path.startswith("/en/blog/"):
        article = page.props.get("data", {})
        if not article.get("title") or not isinstance(article.get("html"), str):
            raise ValueError("BNB article data is missing")
        content = _Page(article["html"])
        result["name"] = article["title"]
        result["links"] = _result_links(content, url)
        result["event_website"] = url.split("#", 1)[0]
        result["published_at"] = _date_time(article.get("published_at"))
        if _RESULT.search(article["title"]):
            result["winners"] = _winner_article(content)
    else:
        event = _cms(page).get("activeHackathonProgram", {})
        if not event.get("title"):
            raise ValueError("BNB hackathon detail data is missing")
        result["name"] = event["title"]
        result["links"] = _result_links(page, url)
        result["event_website"] = url.split("#", 1)[0]
        result["event_status"] = event.get("status")
        for field, kind, label in (
            ("start", "starts", "Event starts"),
            ("end", "ends", "Event ends"),
            ("apply_as_hacker_start_time", "registration_open", "Registration opens"),
            ("apply_as_hacker_end_time", "registration_close", "Registration closes"),
            ("submit_project_start_time", "submission_open", "Submissions open"),
            ("submit_project_end_time", "submission_close", "Submissions close"),
        ):
            _add_schedule(schedule, kind, label, event.get(field), event.get("timezone"))
        for line in str(event.get("overview") or "").splitlines():
            week = re.fullmatch(r"\|\s*(Winners? announc(?:ed|ement)|Results?)\s*\|\s*([^|]+?)\s*\|\s*", line, re.I)
            if week:
                label, raw = week.groups()
                _add_schedule(schedule, "results_expected", label, raw)
        for group in event.get("winner_layer") or []:
            category = _clean(group.get("layer1"))
            rank = _clean(group.get("layer2"))
            for winner in group.get("winners") or []:
                name = _clean(winner.get("name"))
                if name:
                    result["winners"].append({
                        "name": name,
                        "category": category,
                        "rank": rank,
                        "url": _clean(winner.get("github") or winner.get("demo")),
                    })
        for field in ("submit_project_url", "apply_as_hacker_url"):
            raw = event.get(field)
            if isinstance(raw, str) and raw.startswith("https://"):
                result[field] = raw
    if result["winners"]:
        result["winner_status"] = "published"
    return result
