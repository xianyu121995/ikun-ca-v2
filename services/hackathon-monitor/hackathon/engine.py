"""Read-only monitor for public Solana and BSC hackathons."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


BEIJING = timezone(timedelta(hours=8), name="UTC+8")
ROOT = Path(__file__).resolve().parent
import sys as _sys
_SOURCES = ROOT / "sources"
if str(_SOURCES) not in _sys.path:
    _sys.path.insert(0, str(_SOURCES))
STATUS = {
    "pending": "待检查",
    "ok": "读取成功",
    "published": "已看到公开名单",
    "empty": "公开页明确返回空名单",
    "not_published": "来源明确显示尚未公开",
    "unverified": "公开状态未确认",
    "unknown": "公开状态未确认",
    "partial": "仅看到部分名单",
    "error": "读取失败",
}
MILESTONE = {
    "submission_close": "提交截止",
    "gallery_expected": "作品名单预计公开",
    "results_expected": "获奖名单预计公开",
    "awards_ceremony": "颁奖仪式",
    "demo": "路演",
    "starts": "赛事开始",
    "ends": "赛事结束",
    "judging_end": "评审截止",
    "registration_open": "报名开始",
    "registration_close": "报名截止",
    "submission_open": "提交开始",
}
DISCOVERY = (
    "https://www.bnbchain.org/en/hackathons",
    "https://www.bnbchain.org/en/blog",
    "https://luma.com/BNBChainEvents?k=c",
)
BANGKOK = "bnb-bangkok-2026"
HACKQUEST_BANGKOK = "https://www.hackquest.io/hackathons/BNB-Bangkok"
BNB_BANGKOK = "https://www.bnbchain.org/en/blog/bnb-bangkok-build-demo-and-pitch"
AI_TRADING = "https://www.bnbchain.org/en/hackathons/bnbhack-twt-cmc"
TOKENIZED_STOCKS = "https://www.bnbchain.org/en/hackathons/tokenized-stocks"
BANGKOK_SOURCES = (
    (HACKQUEST_BANGKOK, "hackquest"),
    (BNB_BANGKOK, "bnb-news"),
    ("https://luma.com/5topfryz", "luma-event"),
    ("https://luma.com/n5y1y7cu", "luma-event"),
)
PUBLIC_STATUSES = {"published", "partial", "empty"}
PUBLICATION_MILESTONES = {"gallery_expected", "results_expected"}
FINAL_STAGES = {"complete", "completed", "finalized", "finished", "awarded", "results_published", "ended", "archived"}
PENDING_STAGES = {"judging", "voting", "pending_results", "awaiting_results", "submissions_closed"}
ACTIVE_STAGES = {"live", "active", "open", "launched", "registration", "register",
                 "submission", "submissions_open", "in_progress"}
FUTURE_STAGES = {"scheduled", "upcoming", "announced", "registration_open", "funding"}
ATTACHED_KINDS = {"hackquest", "dorahacks", "luma-event", "bnb-news", "external"}



def clock():
    return datetime.now(BEIJING)


def iso(value):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed.tzinfo else None


def present_time(value):
    exact = iso(value)
    if exact:
        return exact.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    return value or "待确认"


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def event_stage(value):
    state = normalized(value).replace("-", "_").replace(" ", "_")
    if state in FINAL_STAGES:
        return "completed"
    if state in PENDING_STAGES:
        return "awaiting_results"
    if state in ACTIVE_STAGES:
        return "active"
    if state in FUTURE_STAGES:
        return "scheduled"
    return "unknown"


def chain_label(value):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(dict.fromkeys(str(item) for item in value if item))
    return str(value) if value else None


def publication_schedule(payload):
    return sorted({
        (item["kind"], instant.astimezone(timezone.utc).isoformat() if instant else
         (item.get("time") or item.get("label") or ""))
        for item in payload.get("schedule", [])
        if item["kind"] in PUBLICATION_MILESTONES
        for instant in [iso(item.get("time"))]
    })


def plain_text(value):
    if isinstance(value, str):
        text = " ".join(value.split())
        return text or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def rank_identity(rank):
    value = normalized(rank)
    numeric = re.fullmatch(r"(?:place\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+place)?", value)
    return numeric[1] if numeric else value


def public_website(value):
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.strip()
    if "://" not in url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not host or "." not in host or any(char.isspace() for char in url):
        return None
    if parts.username or parts.password:
        return None
    blocked = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", "github.com", "www.github.com",
               "youtube.com", "www.youtube.com", "youtu.be", "loom.com", "www.loom.com", "t.me",
               "discord.com", "discord.gg", "bscscan.com", "testnet.bscscan.com"}
    if host in blocked:
        return None
    return url.split("#", 1)[0]


def public_twitter(value):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("@"):
        raw = raw[1:]
    if re.fullmatch(r"[A-Za-z0-9_]{1,15}", raw):
        return f"https://x.com/{raw}"
    if "://" not in raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.scheme != "https" or host not in {"x.com", "twitter.com"} or parts.username:
        return None
    handle = parts.path.strip("/").split("/")[0]
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) or handle.lower() in {"intent", "share", "home", "search"}:
        return None
    return f"https://x.com/{handle}"


def brief(value):
    if not isinstance(value, str):
        return None
    text = " ".join(re.sub(r"<[^>]+>", " ", value).split())
    if not text or re.search(r"\b(?:password|passwd|secret|api[_ -]?key|private key|mnemonic|seed phrase)\b", text, re.I):
        return None
    if len(text) <= 160:
        return text
    short = text[:160]
    return short.rsplit(" ", 1)[0] if " " in short else short


def count_public(payload, default):
    return next((payload.get(field) for field in
                 ("public_gallery_count", "public_submission_count", "public_project_count")
                 if payload.get(field) is not None), default)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
                url TEXT PRIMARY KEY, event_id TEXT NOT NULL, kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', checked_at TEXT,
                last_success TEXT, error TEXT, data TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS findings (
                event_id TEXT NOT NULL, kind TEXT NOT NULL, identity TEXT NOT NULL,
                name TEXT NOT NULL, category TEXT, rank TEXT, url TEXT,
                source TEXT NOT NULL, first_seen TEXT NOT NULL, published_at TEXT,
                PRIMARY KEY (event_id, kind, identity)
            );
            CREATE TABLE IF NOT EXISTS updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL, seen_at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery (
                url TEXT PRIMARY KEY, checked_at TEXT NOT NULL, last_success TEXT, error TEXT
            );
        """)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for table, changes in (
                ("events", {"chain": "TEXT", "stage": "TEXT NOT NULL DEFAULT 'unknown'",
                            "pinned": "INTEGER NOT NULL DEFAULT 0"}),
                ("findings", {"chain": "TEXT", "website": "TEXT", "twitter": "TEXT", "info": "TEXT"}),
            ):
                existing = {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}
                for column, definition in changes.items():
                    if column not in existing:
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def close(self):
        self.db.close()

    def add_source(self, event, url, kind, name, *, chain=None, stage=None, pinned=False, alert_at=None):
        notices = []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.source(url)
            if existing:
                event = existing["event_id"]
            enrolled = self.db.execute(
                "INSERT OR IGNORE INTO events (id,name,chain,stage,pinned) VALUES (?,?,?,?,?)",
                (event, name, chain_label(chain), event_stage(stage), int(pinned)),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO sources (url,event_id,kind) VALUES (?,?,?)", (url, event, kind),
            )
            existing_event = self.db.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
            chains = ", ".join(dict.fromkeys(
                value.strip() for label in (existing_event["chain"], chain_label(chain)) if label
                for value in label.split(",") if value.strip()
            ))
            self.db.execute("UPDATE events SET chain=?,pinned=MAX(pinned,?) WHERE id=?",
                            (chains or None, int(pinned), event))
            if enrolled.rowcount and alert_at:
                notice = {"kind": "new_event", "event": name, "chain": chains or None, "at": alert_at,
                          "source": url}
                notices.append(self.save_update(event, notice))
        return notices

    def save_update(self, event_id, notice):
        inserted = self.db.execute(
            "INSERT INTO updates (event_id,seen_at,kind,data) VALUES (?,?,?,?)",
            (event_id, notice["at"], notice["kind"], json.dumps(notice, ensure_ascii=False)),
        )
        return {"id": inserted.lastrowid, "event_id": event_id, **notice}

    def updates(self, event_match="", after_id=0):
        rows = self.db.execute("""
            SELECT updates.*,COALESCE(events.name,updates.event_id) AS name
            FROM updates LEFT JOIN events ON updates.event_id=events.id
            WHERE updates.id>? ORDER BY updates.id
        """, (after_id,))
        return [{"id": row["id"], "event_id": row["event_id"], **json.loads(row["data"])}
                for row in rows if matches(row["event_id"], row["name"], event_match)]

    def discovery_status(self, source):
        return self.db.execute("SELECT * FROM discovery WHERE url=?", (source,)).fetchone()

    def save_discovery(self, source, seen, error=None):
        with self.db:
            self.db.execute("""
                INSERT INTO discovery (url,checked_at,last_success,error) VALUES (?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET checked_at=excluded.checked_at,
                  last_success=COALESCE(excluded.last_success,discovery.last_success),error=excluded.error
                WHERE discovery.checked_at<=excluded.checked_at
            """, (source, seen, None if error else seen, error))

    def regroup_new_source(self, url, event_id):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.source(url)
            if not row or row["last_success"] or row["event_id"] == event_id:
                return
            self.db.execute("UPDATE sources SET event_id=? WHERE url=?", (event_id, url))
            self.db.execute("""
                DELETE FROM events WHERE id=?
                AND NOT EXISTS (SELECT 1 FROM sources WHERE event_id=?)
                AND NOT EXISTS (SELECT 1 FROM findings WHERE event_id=?)
            """, (row["event_id"], row["event_id"], row["event_id"]))

    def source(self, url):
        return self.db.execute("SELECT * FROM sources WHERE url=?", (url,)).fetchone()

    def targets(self, event_match):
        rows = self.db.execute("""
            SELECT sources.*, events.name, events.chain, events.stage, events.pinned
            FROM sources JOIN events ON sources.event_id=events.id
            ORDER BY events.name, sources.url
        """)
        return [row for row in rows if matches(row["event_id"], row["name"], event_match)]

    def fail(self, url, seen, error):
        with self.db:
            self.db.execute("""
                UPDATE sources SET status='error',checked_at=?,error=?
                WHERE url=? AND (checked_at IS NULL OR checked_at<=?)
            """, (seen, error, url, seen))

    def record(self, url, seen, payload):
        notices, winners = [], []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            source = self.source(url)
            if source["checked_at"] and source["checked_at"] > seen:
                return notices
            event = self.db.execute("SELECT * FROM events WHERE id=?", (source["event_id"],)).fetchone()
            previous = json.loads(source["data"])
            current = {key: value for key, value in payload.items()
                       if key not in {"submissions", "winners", "links"}}
            if not current.get("schedule") and previous.get("schedule"):
                current["schedule"] = previous["schedule"]
            for kind in ("submission", "winner"):
                key = kind + "_list_seen"
                if previous.get(key):
                    current[key] = previous[key]
                elif current.get(kind + "_status") in PUBLIC_STATUSES:
                    current[key] = seen

            base = {"event": event["name"], "chain": event["chain"], "source": url, "at": seen}
            if (source["last_success"] and publication_schedule(current) and
                    publication_schedule(current) != publication_schedule(previous)):
                schedule = [slot for slot in current["schedule"] if slot["kind"] in PUBLICATION_MILESTONES]
                notices.append({"kind": "schedule", **base, "schedule": schedule})

            had_submissions = self.db.execute("""
                SELECT 1 FROM findings WHERE event_id=? AND kind='submission' LIMIT 1
            """, (event["id"],)).fetchone()
            new_submissions = 0
            for kind, field in (("submission", "submissions"), ("winner", "winners")):
                for row in payload.get(field, []):
                    name = row["name"].strip()
                    if not name:
                        continue
                    category, rank = plain_text(row.get("category")), plain_text(row.get("rank"))
                    chain = chain_label(row.get("chain") or row.get("chains"))
                    website, twitter = public_website(row.get("website")), public_twitter(row.get("twitter"))
                    info = brief(row.get("info"))
                    if kind == "winner":
                        identity = "|".join((normalized(name), normalized(category), rank_identity(rank)))
                    else:
                        identity = str(row.get("id") or row.get("url") or normalized(name))
                    published = row.get("published_at")
                    if kind == "winner" and not published:
                        published = payload.get("published_at")
                    inserted = self.db.execute("""
                        INSERT OR IGNORE INTO findings
                        (event_id,kind,identity,name,category,rank,url,source,first_seen,published_at,chain,website,twitter,info)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (event["id"], kind, identity, name, category, rank, row.get("url"),
                          url, seen, published, chain, website, twitter, info))
                    if inserted.rowcount:
                        if kind == "submission":
                            new_submissions += 1
                        else:
                            winners.append({"name": name, "category": category, "rank": rank,
                                            "chain": chain, "url": row.get("url"), "published_at": published})
                    else:
                        self.db.execute("""
                            UPDATE findings SET name=?, published_at=COALESCE(published_at,?),
                                url=COALESCE(?,url), chain=COALESCE(?,chain), category=COALESCE(?,category),
                                website=?, twitter=?, info=?
                            WHERE event_id=? AND kind=? AND identity=?
                        """, (name, published, row.get("url"), chain, category, website, twitter, info,
                              event["id"], kind, identity))
            if not had_submissions and new_submissions:
                notices.append({"kind": "gallery_opened", **base,
                                "count": count_public(current, new_submissions)})
            if winners:
                notices.append({"kind": "winner", **base, "items": winners})
            self.db.execute("""
                UPDATE sources SET status='ok',checked_at=?,last_success=?,error=NULL,data=?
                WHERE url=?
            """, (seen, seen, json.dumps(current, ensure_ascii=False), url))
            return [self.save_update(event["id"], notice) for notice in notices]

    def refresh_stages(self, event_ids, now):
        with self.db:
            for event_id in event_ids:
                source_rows = list(self.db.execute(
                    "SELECT data,status FROM sources WHERE event_id=?", (event_id,)))
                all_data = [json.loads(row["data"]) for row in source_rows]
                incomplete = any(row["status"] in {"error", "pending"} for row in source_rows) or any(
                    "error" in (item.get("submission_status"), item.get("winner_status")) for item in all_data
                )
                stages = {event_stage(item.get("event_status")) for item in all_data}
                results = {item.get("winner_status") for item in all_data}
                dates = [iso(slot.get("time")) for item in all_data for slot in item.get("schedule", [])
                         if slot["kind"] == "submission_close"]
                if "completed" in stages and "published" in results:
                    stage = "collection_incomplete" if incomplete else "completed"
                elif "partial" in results or ("not_published" in results and "published" in results):
                    stage = "awaiting_results"
                elif "completed" in stages or "published" in results:
                    stage = "collection_incomplete" if incomplete else "completed"
                elif "awaiting_results" in stages or (
                    any(date and date <= now for date in dates) and "not_published" in results
                ):
                    stage = "awaiting_results"
                elif "active" in stages:
                    stage = "active"
                elif "scheduled" in stages:
                    stage = "scheduled"
                else:
                    continue
                self.db.execute("UPDATE events SET stage=? WHERE id=?", (stage, event_id))

    def events(self, event_match=""):
        result = []
        for event in self.db.execute("SELECT * FROM events ORDER BY name"):
            if not matches(event["id"], event["name"], event_match):
                continue
            found = self.db.execute("""
                SELECT * FROM findings WHERE event_id=? ORDER BY kind,first_seen,category,rank,name
            """, (event["id"],))
            sources = self.db.execute("SELECT * FROM sources WHERE event_id=? ORDER BY url", (event["id"],))
            result.append({**dict(event), "findings": [dict(row) for row in found],
                           "sources": [{**dict(row), "data": json.loads(row["data"])} for row in sources]})
        return result


def matches(event_id, name, query):
    return not query or normalized(query) in normalized(event_id + " " + name)


def publication_summary(event, now):
    schedules = [item | {"source": source["url"]}
                 for source in event["sources"] for item in source["data"].get("schedule", [])]
    deadlines = [iso(row.get("time")) for row in schedules if row["kind"] == "submission_close"]
    deadlines = {value for value in deadlines if value}
    close = next(iter(deadlines)) if len(deadlines) == 1 else None
    result = {"schedule": schedules, "submission_close": close.isoformat() if close else None}
    for kind, expected_kind in (("submission", "gallery_expected"), ("winner", "results_expected")):
        found = [row for row in event["findings"] if row["kind"] == kind]
        observations = [row["first_seen"] for row in found]
        observations.extend(source["data"][kind + "_list_seen"] for source in event["sources"]
                            if source["data"].get(kind + "_list_seen"))
        observed = min(observations, key=iso, default=None)
        publications = [row["published_at"] for row in found if row["published_at"]]
        exact_dates = [value for value in publications if iso(value)]
        published = (min(exact_dates, key=iso) if exact_dates
                     else min(publications, default=None))
        expected = [row for row in schedules if row["kind"] == expected_kind]
        exact_expected = {iso(row.get("time")) for row in expected} - {None}
        expected_at = next(iter(exact_expected)) if len(exact_expected) == 1 else None
        known_time = iso(published)
        actual = known_time or iso(observed)
        elapsed = round((actual - close).total_seconds() / 3600, 2) if actual and close else None
        result[kind] = {
            "first_seen": observed, "published_at": published, "expected": expected,
            "expected_in_hours": round((expected_at - now).total_seconds() / 3600, 2) if expected_at else None,
            "elapsed_hours": elapsed,
            "elapsed_basis": ("published_at" if known_time else "first_seen") if elapsed is not None else None,
        }
    return result


def canonical(url):
    part = urlsplit(url)
    if part.scheme != "https" or not part.hostname or part.username or part.password:
        raise ValueError("来源必须是公开 HTTPS 链接")
    host = {"hackquest.io": "www.hackquest.io", "bnbchain.org": "www.bnbchain.org",
            "www.dorahacks.io": "dorahacks.io", "lu.ma": "luma.com"}.get(part.hostname, part.netloc.casefold())
    path = part.path.rstrip("/") or "/"
    if host == "dorahacks.io" and path.startswith("/hackathon/"):
        path = "/".join(path.split("/")[:3])
    if host == "earn.superteam.fun":
        host = "superteam.fun"
    if host == "superteam.fun" and path.startswith(("/listing/", "/hackathon/")):
        path = "/earn" + path
    query = {}
    if host in {"colosseum.com", "www.colosseum.com"}:
        query = {key: values[0] for key, values in parse_qs(part.query).items()
                 if key in {"hackathonId", "year"}}
    return urlunsplit((part.scheme, host, path, urlencode(query), ""))


def source_kind(url):
    parts = urlsplit(url)
    host, path = parts.hostname, parts.path
    if host in {"www.hackquest.io", "hackquest.io"} and path.startswith("/hackathons/"):
        return "hackquest"
    if host == "hackathons.solana.com" and path.startswith("/hackathons/"):
        return "solana"
    if host in {"colosseum.com", "www.colosseum.com"} and path not in {"", "/", "/events"}:
        return "colosseum"
    if host in {"superteam.fun", "earn.superteam.fun"} and path.startswith(
        ("/earn/listing/", "/earn/hackathon/", "/listing/", "/hackathon/")
    ):
        return "external"
    if host in {"www.dorahacks.io", "dorahacks.io"} and path.startswith("/hackathon/"):
        return "dorahacks"
    if host in {"www.bnbchain.org", "bnbchain.org"}:
        if path.startswith("/en/hackathons/"):
            return "bnb-event"
        if path.startswith("/en/blog/"):
            return "bnb-news"
    if host in {"luma.com", "lu.ma"} and path.count("/") == 1:
        return "luma-event"
    if host in {"www.binance.com", "binance.com"} and "/support/announcement/detail/" in path:
        return "binance-announcement"
    return None


def fetch(url, timeout):
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; SolBscHackathonMonitor/2.0)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
    })
    with urlopen(request, timeout=timeout) as response:
        data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError("响应超过 6 MB")
        return data.decode(response.headers.get_content_charset("utf-8"), errors="replace")


def adapt(row, timeout):
    url, kind = row["url"], row["kind"]
    if kind == "hackquest":
        from hackquest_source import fetch_hackquest
        gallery = url + "?" + urlencode({"tab": "projectGallery"})
        return fetch_hackquest(gallery, fetch(gallery, timeout), timeout=timeout)
    if kind == "dorahacks":
        from dorahacks_source import read_dorahacks
        return read_dorahacks(url, lambda target: fetch(target, timeout))
    if kind == "solana":
        from solana_source import fetch_solana
        return fetch_solana(url, fetch, timeout=timeout)
    if kind == "colosseum":
        from colosseum_source import fetch_colosseum
        return fetch_colosseum(url, fetch, timeout=timeout)
    if kind == "external":
        from external_sources import fetch_external
        return fetch_external(url, fetch, timeout=timeout)
    if kind == "binance-announcement":
        from hackathon.binance_feed import fetch_binance_announcement
        return fetch_binance_announcement(url, timeout)
    from bnb_sources import parse_bnb
    return parse_bnb(url, fetch(url, timeout))


def discovery_event_id(row, url):
    name = normalized(row["name"])
    if (name in {"bnb bangkok", "bnb demo night: bangkok", "bnb bangkok: build, demo, and pitch"}
            and row.get("event_year") in (None, 2026, "2026")):
        return BANGKOK
    if "tokenized stocks edition" in name:
        return TOKENIZED_STOCKS
    if "ai trading agent edition" in name:
        return AI_TRADING
    linked = {canonical(link) for link in row.get("links", []) if source_kind(link) == "bnb-event"}
    return next(iter(linked)) if row["kind"] == "bnb-news" and len(linked) == 1 else url


def in_scope(row, seen, baseline):
    """Enroll an official page, including ended events and results posts.

    Cancelled and sponsor-seeking pages stay out. The first scan still does not
    alert; newly_published decides that separately.
    """
    raw = normalized(row.get("event_status") or row.get("stage"))
    if raw in {"cancelled", "canceled", "seeking sponsors", "seeking_sponsors"}:
        return False
    if row.get("kind") in {"bnb-event", "bnb-news", "solana", "colosseum", "hackquest", "external", "luma-event", "dorahacks", "binance-announcement"}:
        return True
    if event_stage(raw) != "unknown":
        return True
    if any(moment and moment >= seen for moment in map(iso, (row.get("start_at"), row.get("end_at")))):
        return True
    return False


def newly_published(row, baseline):
    """Alert only for something that showed up after the first successful scan."""
    if not baseline:
        return False
    raw = normalized(row.get("event_status") or row.get("stage"))
    article = row.get("article_date") if isinstance(row.get("article_date"), str) else ""
    end = row.get("end_at") if isinstance(row.get("end_at"), str) else ""
    marker = (article or end)[:10]
    historical = event_stage(raw) == "completed" or raw in {"ended", "archived"} or row.get("is_results")
    if historical:
        return bool(marker) and marker >= str(baseline)[:10]
    return True


def publication_settled(store, event_id):
    """True once every source has read an official winner list, including an explicit empty one."""
    rows = list(store.db.execute("SELECT data, status FROM sources WHERE event_id=?", (event_id,)))
    if not rows:
        return False
    for row in rows:
        if row["status"] in {"error", "pending", None}:
            return False
        try:
            data = json.loads(row["data"] or "{}")
        except json.JSONDecodeError:
            return False
        if data.get("winner_status") not in PUBLIC_STATUSES:
            return False
    return True


def add_discovery(store, rows, source, seen):
    previous = store.discovery_status(source)
    baseline = previous["last_success"] if previous else None
    notices = []
    for item in rows:
        url, kind, name = canonical(item["url"]), item["kind"], item["name"]
        event_id = discovery_event_id(item, url)
        known = store.db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone()
        if not known and not store.source(url) and not in_scope(item, iso(seen), baseline):
            continue
        notices.extend(store.add_source(event_id, url, kind, name,
                                        chain=item.get("chain") or ("BSC" if kind.startswith("bnb-") else None),
                                        stage=item.get("event_status") or item.get("stage"),
                                        alert_at=seen if newly_published(item, baseline) else None))
        if event_id == BANGKOK:
            for link, adapter in BANGKOK_SOURCES:
                store.add_source(event_id, link, adapter, "BNB Bangkok 2026", chain="BSC")
    store.save_discovery(source, seen)
    return notices


def run_pass(store, event_match, timeout, skip_discovery, include_completed=False, blog_pages=1):
    from bnb_sources import discover_bnb
    from hackquest_source import DIRECTORY as HACKQUEST_DIRECTORY, discover_hackquest

    def index(url):
        return discover_bnb(url, fetch(url, timeout))

    notices, failures, touched = [], [], set()
    with ThreadPoolExecutor(max_workers=5) as executor:
        if not skip_discovery:
            from solana_source import discover_solana
            from colosseum_source import discover_colosseum
            from external_sources import discover_external

            jobs = [("https://www.bnbchain.org/en/hackathons", executor.submit(index, DISCOVERY[0])),
                    (HACKQUEST_DIRECTORY, executor.submit(discover_hackquest, timeout)),
                    ("https://hackathons.solana.com/hackathons", executor.submit(discover_solana, timeout)),
                    ("https://colosseum.com/hackathon", executor.submit(discover_colosseum, timeout)),
                    ("https://superteam.fun/earn", executor.submit(discover_external, timeout)),
                    (DISCOVERY[2], executor.submit(index, DISCOVERY[2]))]
            for page in range(1, max(1, int(blog_pages or 1)) + 1):
                blog_url = DISCOVERY[1] if page == 1 else f"{DISCOVERY[1]}?page={page}"
                jobs.append((blog_url, executor.submit(index, blog_url)))
            for url, job in jobs:
                try:
                    rows = job.result()
                    updates = add_discovery(store, rows, url, clock().isoformat(timespec="seconds"))
                    notices.extend(item for item in updates if matches(item["event_id"], item["event"], event_match))
                except (OSError, ValueError, KeyError, TypeError) as error:
                    store.save_discovery(url, clock().isoformat(timespec="seconds"), str(error))
                    failures.append({"source": url, "error": str(error)})

        processed = set()
        while True:
            settled = {}
            targets = []
            for row in store.targets(event_match):
                if row["url"] in processed:
                    continue
                if include_completed or row["pinned"] or row["stage"] != "completed":
                    targets.append(row)
                    continue
                event_id = row["event_id"]
                if event_id not in settled:
                    settled[event_id] = publication_settled(store, event_id)
                if not settled[event_id]:
                    targets.append(row)
            if not targets:
                break
            jobs = [(row, executor.submit(adapt, row, timeout)) for row in targets]
            for row, job in jobs:
                url = row["url"]
                processed.add(url)
                try:
                    payload = job.result()
                    seen = clock().isoformat(timespec="seconds")
                    event_id, event_name = row["event_id"], row["name"]
                    references = payload.get("links", [])
                    if row["kind"] == "bnb-news" and event_id == url and payload.get("winners"):
                        links = {canonical(link) for link in references if source_kind(link) == "bnb-event"}
                        if len(links) == 1:
                            official = store.source(next(iter(links)))
                            if official:
                                store.regroup_new_source(url, official["event_id"])
                                event_id = store.source(url)["event_id"]
                                event_name = store.db.execute(
                                    "SELECT name FROM events WHERE id=?", (event_id,)
                                ).fetchone()["name"]
                    notices.extend(store.record(url, seen, payload))
                    touched.add(event_id)
                    for linked in references:
                        kind = source_kind(linked)
                        if kind in ATTACHED_KINDS:
                            store.add_source(event_id, canonical(linked), kind, event_name, chain=row["chain"])
                    for key in ("submission_error", "winner_error", "schedule_error"):
                        if payload.get(key):
                            failures.append({"source": url, "error": payload[key]})
                except (OSError, ValueError, KeyError, TypeError) as error:
                    store.fail(url, clock().isoformat(timespec="seconds"), str(error))
                    failures.append({"source": url, "error": str(error)})
    store.refresh_stages(touched, clock())
    return notices, failures


def render_events(events, as_json):
    now = clock()
    if as_json:
        print(json.dumps([event | {"publication": publication_summary(event, now)} for event in events],
                         ensure_ascii=False, indent=2))
        return
    if not events:
        print("没有符合筛选条件的赛事。")
    for event in events:
        suffix = f" [{event['chain']}]" if event.get("chain") else ""
        phases = {"scheduled": "已定档", "active": "进行中", "awaiting_results": "待公布结果",
                  "completed": "已结束并归档", "unknown": "阶段待核实",
                  "collection_incomplete": "结果已出，部分来源读取待补"}
        print(f"\n{event['name']}{suffix}  {phases.get(event.get('stage'), '')}")
        summary = publication_summary(event, now)
        sorted_schedule = sorted(summary["schedule"], key=lambda row: (row["kind"], row.get("time") or ""))
        for item in sorted_schedule:
            label = MILESTONE.get(item["kind"], item.get("label", item["kind"]))
            when = present_time(item.get("time")) if item.get("time") else item.get("label") or "待确认"
            print(f"  {label}  {when}  [{item['source']}]")
        for kind, label in (("submission", "提交项目"), ("winner", "获奖项目")):
            part = summary[kind]
            rows = [row for row in event["findings"] if row["kind"] == kind]
            if rows:
                print(f"  {label}  已记录 {len(rows)} 项")
            else:
                states = {source["data"].get(kind + "_status") for source in event["sources"]
                          if source["status"] == "ok"}
                if "empty" in states:
                    print(f"  {label}  公开名单为空")
                elif "not_published" in states:
                    print(f"  {label}  来源显示尚未公开")
                else:
                    print(f"  {label}  名单未读到")
            if part["published_at"]:
                print(f"    公告实际发布时间  {present_time(part['published_at'])}")
            if part["first_seen"]:
                print(f"    首次抓到  {present_time(part['first_seen'])}")
            if part["elapsed_hours"] is not None:
                basis = "实际公布" if part["elapsed_basis"] == "published_at" else "首次抓到"
                hours = part["elapsed_hours"]
                relation = "提交截止后" if hours >= 0 else "提交截止前"
                print(f"    {relation} {abs(hours):g} 小时（按{basis}算）")
            if not part["expected"] and not rows:
                print("    预计公开时间  暂无可核实的公告")
            remaining = part["expected_in_hours"]
            if remaining is not None and not rows:
                label = "距离预计公开" if remaining >= 0 else "超过预计公开时间"
                print(f"    {label}  {abs(remaining):g} 小时")
            for row in rows:
                detail = " · ".join(str(value) for value in (row["chain"], row["category"], row["rank"]) if value)
                details = "  " + detail if detail else ""
                print(f"    - {row['name']}{details}  {row['url'] or row['source']}")
        for source in event["sources"]:
            extra = " / ".join(f"{label}：{STATUS[source['data'][key]]}"
                               for key, label in (("submission_status", "提交"), ("winner_status", "获奖"))
                               if source["data"].get(key) in STATUS)
            label = STATUS.get(source["status"], source["status"])
            if source["status"] == "error":
                label += "  " + source["error"]
            print(f"  来源  {label}" + (f"  {extra}" if extra else "") + f"  {source['url']}")
            data = source["data"]
            if "public_gallery_count" in data:
                public, total = data["public_gallery_count"], data.get("platform_project_count")
                print(f"    公开展厅 {public} 项" + (f"，赛事页计数 {total} 项" if total is not None else ""))
            if "winner_tracks_total" in data:
                print(f"    获奖赛道已公布 {data['winner_tracks_published']}/{data['winner_tracks_total']}")
            for key in ("submission_error", "winner_error"):
                if data.get(key):
                    print(f"    {data[key]}")


def render_scan(notices, failures, show_items=True):
    for item in notices if show_items else ():
        label = item["event"]
        if item.get("chain"):
            label += f" [{item['chain']}]"
        kind = item["kind"]
        if kind == "new_event":
            print(f"新赛事  {label}  {item['source']}")
        elif kind == "gallery_opened":
            print(f"首次看到公开作品名单  {label}  {item['count']} 项  {item['source']}")
        elif kind == "schedule":
            print(f"名单公布时间更新  {label}  {item['source']}")
            for slot in item["schedule"]:
                when = present_time(slot.get("time")) if slot.get("time") else slot.get("label", "待确认")
                print(f"  {MILESTONE.get(slot['kind'], slot['kind'])}  {when}")
        elif kind == "winner":
            print(f"获奖名单公布  {label}  {item['source']}")
            for award in item["items"]:
                detail = " · ".join(str(value) for value in
                                    (award.get("chain"), award.get("category"), award.get("rank")) if value)
                print(f"  {award['name']}" + (f"  {detail}" if detail else "") +
                      (f"  {award['url']}" if award.get("url") else ""))
    for failure in failures:
        print(f"读取失败  {failure['source']}  {failure['error']}", file=sys.stderr)
    if not notices:
        print("本轮没有确认到关键变化。" if not failures else "本轮没有确认到关键变化，部分来源读取失败。")
    elif not show_items:
        print(f"本轮记录 {len(notices)} 条关键变化，详见下方赛事报告。")

