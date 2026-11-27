"""One standing collection cycle. Events are updated or archived, never deleted."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .classify import announcement_in_scope, blog_role
from .parse_announcement import merge_articles, parse_article
from .parse_blog import listing_posts, parse_post, post_url
from .parse_colosseum import directory_url, eternal_draft, hackathon_to_draft, projects_from_page, projects_page_url
from .parse_program import active_program, detail_url, index_programs, program_to_draft, updated_marker, winners_embedded
from .parse_solana import detail_url as solana_detail_url
from .parse_solana import hub_to_draft, parse_detail_projects, parse_hub
from .textutil import next_data

_STOP = {
    "bnb", "chain", "hackathon", "hack", "edition", "the", "of", "with", "and", "meet",
    "winners", "winner", "for", "binance", "web3", "wallet", "official", "build",
}


class CycleError(RuntimeError):
    pass


def run_cycle(cfg: dict, client, store, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    report = {"index": 0, "details": 0, "blog": 0, "announcements": 0, "solana": 0, "colosseum": 0, "errors": []}
    programs = _index(cfg, client, store, current, report)
    if programs is not None:
        _details(cfg, client, store, current, programs, report)
    _blog(cfg, client, store, current, report)
    _announcements(cfg, client, store, current, report)
    _solana(cfg, client, store, current, report)
    _colosseum(cfg, client, store, current, report)
    store.set_meta("last_cycle_at", current.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return report


def _fetch_text(client, url: str, headers: dict | None = None) -> str:
    status, body = client.fetch(url, headers)
    if status != 200:
        raise CycleError(f"HTTP {status}")
    return body.decode("utf-8", "replace")


def _index(cfg, client, store, now, report):
    url = cfg["sources"]["hackathon_index"]
    try:
        page = _fetch_text(client, url)
        data = next_data(page) or {}
        programs = index_programs((data.get("props") or {}).get("pageProps") or {})
        if not programs:
            raise CycleError("目录页没有解析到活动")
        present = set()
        for program in programs:
            draft = program_to_draft(program)
            if draft is None:
                continue
            present.add(draft.id)
            store.upsert(
                draft,
                now,
                replace_projects=winners_embedded(program),
                project_sources={detail_url(program["slug"])} if winners_embedded(program) else set(),
            )
        store.mark_index(present, now)
        store.record_source("bnb-hackathon-index", url, True, "", f"{len(present)} 个目录活动", now)
        report["index"] = len(present)
        return programs
    except Exception as error:  # noqa: BLE001 - one source must not wipe the archive
        store.record_source("bnb-hackathon-index", url, False, type(error).__name__, str(error)[:180], now)
        report["errors"].append(f"index:{type(error).__name__}")
        return None


def _details(cfg, client, store, now, programs, report):
    refresh = int(cfg.get("detail_refresh_seconds") or 21600)
    for program in programs:
        slug = (program.get("slug") or "").strip()
        if not slug:
            continue
        marker = updated_marker(program)
        previous = store.get_meta(f"detail:{slug}") or ""
        fetched_at = previous.split("|", 1)[1] if "|" in previous else ""
        fresh = previous.startswith(f"{marker}|") and marker and _age(fetched_at, now) < refresh
        if fresh:
            continue
        url = detail_url(slug)
        try:
            page = _fetch_text(client, url)
            data = next_data(page) or {}
            detail = active_program((data.get("props") or {}).get("pageProps") or {})
            if detail is None:
                raise CycleError("详情页没有活动记录")
            draft = program_to_draft(detail)
            if draft is None:
                raise CycleError("详情页无法归一")
            store.upsert(draft, now, replace_projects=True, project_sources={url})
            store.set_meta(f"detail:{slug}", f"{updated_marker(detail) or marker}|{now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            store.record_source(f"bnb-detail:{slug}", url, True, "", draft.results_state, now)
            report["details"] += 1
        except Exception as error:  # noqa: BLE001
            store.record_source(f"bnb-detail:{slug}", url, False, type(error).__name__, str(error)[:180], now)
            report["errors"].append(f"detail:{slug}")


def _blog(cfg, client, store, now, report):
    pages = max(1, int(cfg.get("blog_pages_per_cycle") or 2))
    found = {}
    index_ok = True
    for page_no in range(1, pages + 1):
        url = cfg["sources"]["blog"].format(page=page_no)
        try:
            page = _fetch_text(client, url)
            data = next_data(page) or {}
            posts, _total = listing_posts((data.get("props") or {}).get("pageProps") or {})
            for post in posts:
                found[post["slug"]] = post
        except Exception as error:  # noqa: BLE001
            index_ok = False
            store.record_source("bnb-blog", url, False, type(error).__name__, str(error)[:180], now)
            report["errors"].append(f"blog-list:{page_no}")
            break
    pins = [item["slug"] for item in cfg.get("pins") or [] if item.get("kind") == "bnb_blog" and item.get("slug")]
    for slug in pins:
        found.setdefault(slug, {"slug": slug, "title": "", "excerpt": "", "pinned": True})
    if index_ok:
        store.record_source("bnb-blog", cfg["sources"]["blog"].format(page=1), True, "", f"扫描 {len(found)} 篇", now)
    for post in found.values():
        title = post.get("title") or ""
        excerpt = post.get("excerpt") or ""
        pinned = bool(post.get("pinned"))
        role = blog_role(title, excerpt)
        if role is None and not pinned:
            continue
        url = post_url(post["slug"])
        try:
            page = _fetch_text(client, url)
            draft = parse_post(page, post["slug"], title, excerpt)
            if draft is None:
                if pinned:
                    store.record_source(f"bnb-blog:{post['slug']}", url, False, "ParseError", "固定来源没有解析出黑客松内容", now)
                continue
            _save_blog(store, draft, now)
            store.record_source(f"bnb-blog:{post['slug']}", url, True, "", draft.classification, now)
            report["blog"] += 1
        except Exception as error:  # noqa: BLE001
            store.record_source(f"bnb-blog:{post['slug']}", url, False, type(error).__name__, str(error)[:180], now)
            report["errors"].append(f"blog:{post['slug']}")


def _save_blog(store, draft, now):
    """Winner posts attach to the matching catalog event. Unmatched posts stay as their own record."""
    rows = store.events()
    match = best_match(draft.title, [row for row in rows if row["id"] != draft.id])
    source = draft.links[0].url if draft.links else post_url(draft.id.split(":", 1)[-1])
    if match is not None and str(match["id"]).startswith("bnb-hackathon:"):
        if draft.projects:
            store.replace_source_projects(match["id"], source, draft.projects, draft.results_note, now)
        else:
            store.add_link(match["id"], source, "官方博客")
        if draft.id.startswith("bnb-blog:"):
            store.forget_duplicate(draft.id)
        return
    store.upsert(draft, now, replace_projects=True, project_sources=draft.project_sources())


def _announcements(cfg, client, store, now, report):
    codes = {item["code"] for item in cfg.get("pins") or [] if item.get("kind") == "binance_article" and item.get("code")}
    cap = max(1, int(cfg.get("announcement_pages_per_cycle") or 5))
    for catalog in cfg["sources"].get("catalogs") or []:
        cursor = store.get_meta(f"binance-cursor:{catalog}")
        reached = cursor is None
        scanned = []
        url = ""
        try:
            for page_no in range(1, cap + 1):
                url = cfg["sources"]["binance_catalog"].format(catalog=catalog, page=page_no)
                payload = json.loads(_fetch_text(client, url, {"lang": "en"}))
                articles = ((payload.get("data") or {}).get("articles") or []) if isinstance(payload, dict) else []
                if not articles:
                    break
                for article in articles:
                    code = article.get("code")
                    title = article.get("title") or ""
                    if not code:
                        continue
                    scanned.append(code)
                    if cursor and code == cursor:
                        reached = True
                    if announcement_in_scope(title):
                        codes.add(code)
                if reached and cursor:
                    break
            note = f"扫描 {len(scanned)} 条"
            if cursor and not reached:
                note += "；本轮页数上限内没有回到上次位置，游标不前跳"
            elif scanned:
                store.set_meta(f"binance-cursor:{catalog}", scanned[0])
            store.record_source(f"binance-catalog:{catalog}", url, True, "", note, now)
        except Exception as error:  # noqa: BLE001
            store.record_source(f"binance-catalog:{catalog}", url or str(catalog), False, type(error).__name__, str(error)[:180], now)
            report["errors"].append(f"catalog:{catalog}")
    for code in sorted(codes):
        try:
            draft = _article(cfg, client, code)
            if draft is None:
                store.record_source(f"binance:{code}", article_page(code), False, "OutOfScope", "公告标题不是黑客松", now)
                continue
            store.upsert(draft, now, replace_projects=True, project_sources=set())
            store.record_source(f"binance:{code}", article_page(code), True, "", draft.submission_state, now)
            report["announcements"] += 1
        except Exception as error:  # noqa: BLE001
            store.record_source(f"binance:{code}", article_page(code), False, type(error).__name__, str(error)[:180], now)
            report["errors"].append(f"binance:{code}")


def _article(cfg, client, code: str):
    url = cfg["sources"]["binance_article"].format(code=code)
    zh_payload = json.loads(_fetch_text(client, url, {"lang": "zh-CN"}))
    en_payload = json.loads(_fetch_text(client, url, {"lang": "en"}))
    zh = parse_article(zh_payload, code, "zh-CN")
    en = parse_article(en_payload, code, "en")
    return merge_articles(code, zh, en)


def article_page(code: str) -> str:
    return f"https://www.binance.com/zh-CN/support/announcement/detail/{code}"


def best_match(title: str, rows):
    source = _tokens(title)
    if len(source) < 2:
        return None
    scored = []
    for row in rows:
        dest = _tokens(row["title"])
        overlap = source & dest
        if len(overlap) < 2:
            continue
        score = len(overlap) / len(source | dest)
        scored.append((score, len(overlap), row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not scored or scored[0][0] < 0.34:
        return None
    catalog = [item for item in scored if item[0] >= 0.34 and str(item[2]["id"]).startswith("bnb-hackathon:")]
    pool = catalog or scored
    pool.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(pool) > 1 and pool[1][1] == pool[0][1] and pool[1][0] >= pool[0][0] - 0.05:
        return None
    return pool[0][2]


def _solana(cfg, client, store, now, report):
    url = (cfg.get("sources") or {}).get("solana_hub")
    if not url:
        return
    try:
        records = parse_hub(_fetch_text(client, url))
        if not records:
            raise CycleError("Solana 黑客松目录没有解析到活动")
        present = set()
        refresh = int(cfg.get("detail_refresh_seconds") or 21600)
        for record in records:
            draft = hub_to_draft(record)
            draft.touch_submission = False
            draft.touch_results = False
            present.add(draft.id)
            store.upsert(draft, now, replace_projects=False)
            previous = store.get_meta(f"solana-detail:{record['slug']}") or ""
            fetched_at = previous.split("|", 1)[1] if "|" in previous else ""
            if previous and _age(fetched_at, now) < refresh:
                continue
            page_url = solana_detail_url(record["slug"])
            try:
                projects, note, results = parse_detail_projects(_fetch_text(client, page_url), record["slug"])
            except Exception as error:  # noqa: BLE001
                store.record_source(f"solana-detail:{record['slug']}", page_url, False, type(error).__name__, str(error)[:180], now)
                report["errors"].append(f"solana:{record['slug']}")
                continue
            draft.projects = projects
            draft.submission_state = "public" if any(item.role == "submitted" for item in projects) else "not_published"
            draft.submission_note = note
            draft.results_state = "published" if any(item.role == "winner" for item in projects) else "not_published"
            draft.results_note = results
            draft.touch_submission = True
            draft.touch_results = True
            store.upsert(draft, now, replace_all_projects=True)
            stamp = now if now is not None else datetime.now(timezone.utc)
            store.set_meta(f"solana-detail:{record['slug']}", f"ok|{stamp.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            store.record_source(f"solana-detail:{record['slug']}", page_url, True, "", note[:180], now)
        store.mark_index(present, now, prefix="solana-hackathon:", missing_note="Solana 黑客松目录这次没有再列出它。上次核实的内容仍留在归档。")
        store.record_source("solana-hub", url, True, "", f"{len(present)} 个活动", now)
        report["solana"] = len(present)
    except Exception as error:  # noqa: BLE001
        store.record_source("solana-hub", url, False, type(error).__name__, str(error)[:180], now)
        report["errors"].append("solana-hub")


def _colosseum(cfg, client, store, now, report):
    sources = cfg.get("sources") or {}
    url = sources.get("colosseum_directories")
    if not url:
        return
    try:
        payload = json.loads(_fetch_text(client, url, {"Accept": "application/json"}))
        hackathons = [item for item in (payload.get("hackathons") or []) if isinstance(item, dict) and item.get("id")]
        present = set()
        refresh = int(cfg.get("detail_refresh_seconds") or 21600)
        for record in hackathons:
            key = f"colosseum-projects:{record['id']}"
            previous = store.get_meta(key) or ""
            fetched_at = previous.split("|", 1)[1] if "|" in previous else ""
            fresh = bool(previous) and _age(fetched_at, now) < refresh
            if fresh:
                present.add(f"colosseum:{record.get('slug') or record['id']}")
                continue
            try:
                projects, total, solana_only, directory_total = _colosseum_projects(cfg, client, record)
            except Exception as error:  # noqa: BLE001
                store.record_source(f"colosseum:{record.get('slug')}", directory_url(record["id"]), False, type(error).__name__, str(error)[:180], now)
                report["errors"].append(f"colosseum:{record.get('slug')}")
                present.add(f"colosseum:{record.get('slug') or record['id']}")
                continue
            draft = hackathon_to_draft(record, total, solana_only)
            draft.projects = projects
            winners = [item for item in projects if item.role == "winner"]
            draft.submission_state = "public" if projects else "not_published"
            short = total is not None and len(projects) < total
            clipped = " 这次没有把目录翻完，所以下面仍不是目录中的全部公开项目。" if short else ""
            if solana_only:
                draft.submission_note = (
                    f"公开目录共 {directory_total} 个项目，其中链字段为 Solana 的 {total} 个。"
                    f"本次列入 {len(projects)} 个。其他链不在这份名单里。没进公开目录的报名不会出现。{clipped}"
                )
            elif projects:
                draft.submission_note = f"公开目录返回 {total} 个项目，本次列入 {len(projects)} 个。没进目录的报名不会出现，这不是每一份报名表。{clipped}"
            draft.results_state = "published" if winners else "not_published"
            if winners:
                draft.results_note = "只有目录记录里带奖项字段的项目标成获奖。其余公开项目仍在投稿列表。"
            store.upsert(draft, now, replace_all_projects=True)
            stamp = now if now is not None else datetime.now(timezone.utc)
            store.set_meta(key, f"{total}|{stamp.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            present.add(draft.id)
            store.record_source(f"colosseum:{record.get('slug')}", directory_url(record["id"]), True, "", f"{len(projects)} 个公开项目", now)
        store.upsert(eternal_draft(), now, replace_projects=False)
        present.add("colosseum:eternal")
        store.mark_index(present, now, prefix="colosseum:", missing_note="Colosseum 公开目录这次没有再列出它。上次核实的内容仍留在归档。")
        store.record_source("colosseum-directories", url, True, "", f"{len(present)} 届", now)
        report["colosseum"] = len(present)
    except Exception as error:  # noqa: BLE001
        store.record_source("colosseum-directories", url, False, type(error).__name__, str(error)[:180], now)
        report["errors"].append("colosseum")


def _colosseum_projects(cfg, client, record):
    hackathon_id = record["id"]
    probe = json.loads(_fetch_text(client, projects_page_url(hackathon_id, 0, None, limit=1), {"Accept": "application/json"}))
    solana_only = bool(probe.get("hasChainData"))
    directory_total = probe.get("totalCount") if isinstance(probe.get("totalCount"), int) else None
    meta = (probe.get("hackathons") or [{}])[0] if isinstance(probe.get("hackathons"), list) else {}
    if isinstance(meta, dict) and meta.get("startDate"):
        record.update({key: meta.get(key) for key in ("startDate", "endDate", "projectSubmissionStartDate", "projectSubmissionEndDate", "description") if meta.get(key)})
    chain = "solana" if solana_only else None
    projects = []
    total = directory_total
    offset = 0
    pages = 0
    while pages < 80:
        page = json.loads(_fetch_text(client, projects_page_url(hackathon_id, offset, chain, limit=50), {"Accept": "application/json"}))
        batch, page_total = projects_from_page(page, solana_only)
        if isinstance(page_total, int):
            total = page_total
        projects.extend(batch)
        pages += 1
        offset += len(batch) or 100
        if not page.get("hasMore") or not batch:
            break
    if total is not None and len(projects) < total:
        pass
    return projects, total, solana_only, directory_total


def _tokens(title: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", (title or "").lower()) if word not in _STOP and len(word) > 2}


def _age(stamp: str, now: datetime) -> float:
    try:
        then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return 10 ** 12
    return (now - then).total_seconds()
