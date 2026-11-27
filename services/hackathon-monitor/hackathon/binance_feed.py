"""Binance.com public announcement catalogs. HackQuest does not cover these."""

from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .engine import add_discovery, canonical, clock
from .parse_announcement import merge_articles, parse_article

ARTICLE = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}"
CATALOG = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId={catalog}&pageNo={page}&pageSize=20"
_KIND = {
    "submission": "submission_close",
    "review": "judging_end",
    "announcement": "results_expected",
}


def announcement_in_scope_title(title: str) -> bool:
    from .classify import announcement_in_scope
    return announcement_in_scope(title)


def _get(url, timeout, headers=None):
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ikun-hackathon-monitor/1.0)",
        "Accept": "application/json",
        **(headers or {}),
    })
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_binance_announcement(url, timeout=20):
    """Official announcement facts only. The survey form is not a project gallery."""
    code = urlsplit(url).path.rstrip("/").split("/")[-1]
    zh = _get(ARTICLE.format(code=code), timeout, {"lang": "zh-CN"})
    en = _get(ARTICLE.format(code=code), timeout, {"lang": "en"})
    draft = merge_articles(code, parse_article(zh, code, "zh-CN"), parse_article(en, code, "en"))
    if draft is None:
        return {"submission_status": "unverified", "winner_status": "unverified", "schedule": []}
    schedule = []
    for milestone in draft.milestones:
        key = milestone.key.split("-")[-1]
        when = milestone.end_utc or milestone.start_utc
        if not when:
            continue
        schedule.append({
            "kind": _KIND.get(key, "ends"),
            "label": milestone.label,
            "time": when.replace("Z", "+00:00"),
        })
    return {
        "name": draft.title,
        "event_status": "active",
        "submission_status": "not_published",
        "winner_status": "not_published",
        "schedule": schedule,
        "prize": draft.prize,
        "summary": draft.summary,
        "links": [link.url for link in draft.links],
        "form_url": draft.submission_form_url,
    }


def discover_binance(store, catalogs, pages, timeout, get=_get):
    """Find new hackathon announcements. One catalog failure does not stop the others."""
    notices, failures = [], []
    for catalog in catalogs:
        rows = []
        try:
            for page in range(1, pages + 1):
                payload = get(CATALOG.format(catalog=catalog, page=page), timeout, {"lang": "en"})
                articles = ((payload.get("data") or {}).get("articles") or []) if isinstance(payload, dict) else []
                if not articles:
                    break
                for article in articles:
                    title = article.get("title") or ""
                    code = article.get("code")
                    if not code or not announcement_in_scope_title(title):
                        continue
                    url = canonical(f"https://www.binance.com/zh-CN/support/announcement/detail/{code}")
                    rows.append({
                        "name": title,
                        "url": url,
                        "kind": "binance-announcement",
                        "chain": "BSC",
                        "event_status": "active",
                    })
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({"source": f"binance-catalog:{catalog}", "error": str(error)})
            continue
        notices.extend(add_discovery(store, rows, CATALOG.format(catalog=catalog, page=1), clock().isoformat(timespec="seconds")))
    return notices, failures
