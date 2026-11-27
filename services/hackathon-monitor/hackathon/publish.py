"""Build the website snapshot from the change-tracking store. The site never opens sqlite."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .engine import BEIJING, STATUS, iso, present_time, public_twitter, public_website, publication_summary

_CHANGE = {
    "new_event": "新赛事",
    "gallery_opened": "有新名单",
    "schedule": "赛程更新",
    "winner": "有新获奖",
}
_PHASE = {
    "scheduled": "upcoming",
    "active": "live",
    "awaiting_results": "live",
    "submission_closed": "live",
    "completed": "ended",
    "collection_incomplete": "ended",
    "unknown": "unknown",
}
_DOCUMENTS = (
    ("announcement", "原公告"),
    ("gallery", "作品页"),
    ("results", "结果公告"),
)


def _ecosystem(chain: str | None) -> str:
    text = (chain or "").upper()
    has_sol = "SOL" in text
    has_bnb = "BSC" in text or "BNB" in text
    if has_sol and not has_bnb:
        return "solana"
    if has_bnb and not has_sol:
        return "bnb"
    if has_sol and has_bnb:
        return "both"
    return "unknown"


def _status(sources, key: str) -> str:
    values = [source["data"].get(key) for source in sources if source["data"].get(key)]
    for preferred in ("published", "partial", "empty", "error", "not_published", "unverified", "unknown"):
        if preferred in values:
            return "unverified" if preferred == "unknown" else preferred
    if any(source["status"] == "error" for source in sources):
        return "error"
    return "unverified"


def _projects(findings, kind: str):
    rows = []
    for row in findings:
        if row["kind"] != kind or not row.get("name"):
            continue
        source = row.get("source") or row.get("url") or ""
        if not str(source).startswith("https://") and not str(row.get("url") or "").startswith("https://"):
            continue
        rows.append({
            "name": row["name"],
            "role": "winner" if kind == "winner" else "submitted",
            "place": row.get("rank") or "",
            "track": row.get("category") or "",
            "url": row.get("url") or "",
            "source_url": row.get("url") if str(row.get("url") or "").startswith("https://") else source,
            "note": row.get("chain") or "",
            "info": row.get("info") or "",
            "website": public_website(row.get("website")) or "",
            "twitter": public_twitter(row.get("twitter")) or "",
        })
    return rows


def _prize(sources) -> str:
    official = []
    secondary = []
    for source in sources:
        prize = source["data"].get("prize")
        if not prize:
            continue
        if source["kind"] == "hackquest":
            secondary.append(str(prize))
        else:
            official.append(str(prize))
    if official:
        return official[0]
    if secondary:
        return "HackQuest（非主办方奖金，不覆盖官方数字）：" + secondary[0]
    return ""


def _milestones(summary):
    rows = []
    for index, item in enumerate(summary.get("schedule") or []):
        when = item.get("time")
        label = item.get("label") or item.get("kind") or "日程"
        display = present_time(when) + " 北京时间（UTC+8）" if when else label
        source = item.get("source") or ""
        if not source.startswith("https://"):
            continue
        rows.append({
            "key": f"{item.get('kind') or 'slot'}-{index}",
            "label": label,
            "display": display,
            "timezone_label": "Asia/Shanghai",
            "precision": "instant" if iso(when) else "text",
            "source_url": source,
            "start_utc": iso(when).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if iso(when) else None,
            "end_utc": None,
        })
    return rows


def _beijing(value) -> str:
    if isinstance(value, datetime):
        value = value.isoformat()
    if not isinstance(value, str) or iso(value) is None:
        return ""
    return present_time(value) + " 北京时间（UTC+8）"


def _publication(summary, status_name: str, kind: str):
    part = summary.get(kind) or {}
    return {
        "status": status_name,
        "status_label": STATUS.get(status_name, status_name),
        "first_seen": part.get("first_seen"),
        "published_at": part.get("published_at"),
        "first_seen_display": _beijing(part.get("first_seen")),
        "published_at_display": _beijing(part.get("published_at")),
        "elapsed_basis": part.get("elapsed_basis"),
        "elapsed_hours": part.get("elapsed_hours"),
        "expected_in_hours": part.get("expected_in_hours"),
    }


def _side_source(url: str) -> bool:
    return "/earn/listing/" in str(url)


def _document_role(source) -> str:
    url = str(source.get("url") or "")
    kind = source.get("kind") or ""
    data = source.get("data") or {}
    if _side_source(url) or "/earn/hackathon/" in url:
        return ""
    if kind == "binance-announcement":
        return "announcement"
    if kind == "bnb-news":
        return "results" if "winner" in url or data.get("winner_status") == "published" else "announcement"
    if kind in {"hackquest", "solana", "colosseum"} and data.get("submission_status") in {"published", "partial", "empty"}:
        return "gallery"
    if kind == "dorahacks" and data.get("submission_status") in {"published", "partial"}:
        return "gallery"
    return ""


def _documents(sources):
    rows = []
    seen = set()
    for source in sources:
        role = _document_role(source)
        url = source.get("url") or ""
        if not role or not str(url).startswith("https://") or (role, url) in seen:
            continue
        seen.add((role, url))
        rows.append({"role": role, "label": dict(_DOCUMENTS)[role], "url": url})
    return rows


def _side_tracks(sources, findings):
    listings = [source for source in sources if _side_source(source.get("url"))]
    if not listings or len(listings) == len(sources):
        return []
    tracks = []
    for source in listings:
        url = source.get("url") or ""
        if not _side_source(url):
            continue
        own = [row for row in findings if row.get("source") == url]
        data = source.get("data") or {}
        tracks.append({
            "name": data.get("name") or source.get("kind") or url,
            "url": url,
            "label": "Superteam 赛道",
            "note": data.get("scope_note") or "Superteam Earn 赛道结果，不是主办方总榜。",
            "published_at_display": _beijing(data.get("published_at")),
            "first_seen_display": _beijing(next((row.get("first_seen") for row in own if row.get("first_seen")), "")),
            "works": _projects(own, "submission"),
            "winners": _projects(own, "winner"),
        })
    return tracks


def build_site_snapshot(store, now: datetime | None = None) -> dict:
    current = now or datetime.now(BEIJING)
    events = []
    for event in store.events():
        sources = event["sources"]
        main_sources = [source for source in sources if not _side_source(source["url"]) and "/earn/hackathon/" not in source["url"]] or sources
        main_findings = [row for row in event["findings"] if not _side_source(row.get("source"))]
        summary = publication_summary({**event, "findings": main_findings, "sources": main_sources}, current)
        submission_status = _status(main_sources, "submission_status")
        winner_status = _status(main_sources, "winner_status")
        submissions = _projects(main_findings, "submission")
        winners = _projects(main_findings, "winner")
        if submissions and submission_status not in {"published", "partial"}:
            submission_status = "partial"
        if winners and winner_status not in {"published", "partial"}:
            winner_status = "partial"
        stage = event.get("stage") or "unknown"
        if stage == "submission_closed":
            tracking_label = "已截稿"
        elif winner_status in {"published", "partial", "empty"} and stage in {"completed", "collection_incomplete"}:
            tracking_label = "已公布结果"
        else:
            tracking_label = ""
        start = next((row["start_utc"] for row in _milestones(summary) if row["start_utc"]), None)
        website = next((public_website(source["data"].get("event_website")) for source in sources if public_website(source["data"].get("event_website"))), "")
        twitter = next((public_twitter(source["data"].get("event_twitter")) for source in sources if public_twitter(source["data"].get("event_twitter"))), "")
        events.append({
            "id": event["id"],
            "title": event["name"],
            "ecosystem": _ecosystem(event.get("chain")),
            "chain": event.get("chain") or "",
            "website": website or "",
            "twitter": twitter or "",
            "classification": "hackathon",
            "summary": next((source["data"].get("summary") for source in main_sources if source["data"].get("summary")), ""),
            "classification_reason": next((source["data"].get("scope_note") for source in main_sources if source["data"].get("scope_note")), "公开来源收录的黑客松。"),
            "tracking_label": tracking_label,
            "documents": _documents(sources),
            "side_tracks": _side_tracks(sources, event["findings"]),
            "location": "",
            "prize": _prize(sources),
            "official_status": stage,
            "phase": _PHASE.get(stage, "unknown"),
            "phase_basis": "monitor_stage",
            "start_utc": start,
            "end_utc": None,
            "listed": True,
            "missing_note": "",
            "submission": {
                "state": submission_status,
                "note": _note(submission_status, "投稿"),
                "form_url": next((source["data"].get("form_url") for source in sources if source["data"].get("form_url")), None),
                "projects": submissions,
            },
            "results": {
                "state": winner_status,
                "note": _note(winner_status, "获奖"),
                "projects": winners,
            },
            "milestones": _milestones({**summary, "schedule": [item for item in summary.get("schedule") or [] if not _side_source(item.get("source"))]}),
            "links": [{"label": source["kind"], "url": source["url"]} for source in sources if str(source["url"]).startswith("https://")],
            "publication": {
                "submission": _publication(summary, submission_status, "submission"),
                "winner": _publication(summary, winner_status, "winner"),
            },
            "sources": [{
                "url": source["url"],
                "kind": source["kind"],
                "status": source["status"],
                "status_label": STATUS.get(source["status"], source["status"]),
                "submission_status": source["data"].get("submission_status"),
                "winner_status": source["data"].get("winner_status"),
                "error": source.get("error") or "",
            } for source in sources],
        })
    changes = []
    for row in store.updates(after_id=0)[-30:]:
        raw_chain = row.get("chain") or ""
        changes.append({
            "id": row["id"],
            "kind": row["kind"],
            "label": _CHANGE.get(row["kind"], row["kind"]),
            "event": row.get("event") or row.get("event_id"),
            "at": row.get("at"),
            "at_beijing": present_time(row.get("at")) if row.get("at") else "",
            "source": row.get("source") or "",
            "chain": raw_chain,
            "ecosystem": _ecosystem(raw_chain) if raw_chain else "",
        })
    return {
        "schema": "hackathon-snapshot-v1",
        "generated_at": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_beijing": current.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M"),
        "timezone": "Asia/Shanghai",
        "standing": True,
        "sources": [],
        "changes": changes,
        "events": events,
    }


def _note(status: str, kind: str) -> str:
    if status == "published":
        return f"来源已公开{kind}名单。名单以外的项目不会出现。"
    if status == "partial":
        return f"只看到一部分{kind}。这不是全部名单。"
    if status == "empty":
        return f"公开页面明确返回了空的{kind}名单。"
    if status == "not_published":
        return f"来源写明{kind}名单尚未公开。空着不是「已经公布为零」。"
    if status == "error":
        return f"{kind}名单这次没读成。上次成功的记录会保留，不会改写成空名单。"
    return f"{kind}名单尚未核实。没有把缺失当成一份已公布的空名单。"


def write_site_snapshot(path: str, payload: dict):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = path + ".tmp"
    import json
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)
    os.chmod(path, 0o644)
