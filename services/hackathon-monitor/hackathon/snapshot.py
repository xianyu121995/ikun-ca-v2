"""Public snapshot. The website reads this file and never opens the SQLite database."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .store import Store
from .timeutil import beijing_clock, parse_iso

_ENDED = {"ended", "已结束", "complete", "completed", "closed"}


def phase_of(official_status: str | None, start_utc: str | None, end_utc: str | None, now: datetime) -> tuple[str, str]:
    status = (official_status or "").strip().lower()
    if status in _ENDED:
        return "ended", "official_status"
    start = parse_iso(start_utc)
    end = parse_iso(end_utc)
    if start and now < start:
        return "upcoming", "official_window"
    if end and now >= end:
        return "ended", "official_window"
    if start and end and start <= now < end:
        return "live", "official_window"
    if start and end is None and now >= start:
        return "unknown", "open_ended"
    return "unknown", "insufficient"


def build_snapshot(store: Store, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    events = []
    for row in store.events():
        milestones = [_milestone(item) for item in store.milestones(row["id"])]
        projects = _dedupe([item for item in (_project(item) for item in store.projects(row["id"])) if item["source_url"].startswith("https://")])
        submitted = [item for item in projects if item["role"] == "submitted"]
        results = [item for item in projects if item["role"] in {"winner", "selected", "shortlisted"}]
        state, basis = phase_of(row["official_status"], row["start_utc"], row["end_utc"], current)
        submission_state = "public" if submitted else row["submission_state"]
        results_state = "published" if results else row["results_state"]
        events.append({
            "id": row["id"],
            "title": row["title"],
            "ecosystem": row["ecosystem"] if "ecosystem" in row.keys() else "bnb",
            "classification": row["classification"],
            "classification_reason": row["classification_reason"],
            "summary": row["summary"],
            "location": row["location"],
            "prize": row["prize"],
            "official_status": row["official_status"],
            "phase": state,
            "phase_basis": basis,
            "start_utc": row["start_utc"],
            "end_utc": row["end_utc"],
            "listed": bool(row["listed"]),
            "missing_note": row["missing_note"],
            "submission": {
                "state": submission_state,
                "note": row["submission_note"],
                "form_url": row["submission_form_url"],
                "projects": submitted,
            },
            "results": {
                "state": results_state,
                "note": row["results_note"],
                "projects": results,
            },
            "milestones": [item for item in milestones if item["source_url"].startswith("https://") and item["display"]],
            "links": [{"label": item["label"], "url": item["url"]} for item in store.links(row["id"]) if str(item["url"]).startswith("https://")],
        })
    checks = []
    for item in store.sources():
        checks.append({
            "id": item["source_id"],
            "url": item["url"],
            "ok": bool(item["ok"]),
            "checked_at": item["checked_at"],
            "error": item["error"],
            "note": item["note"],
        })
    return {
        "schema": "hackathon-snapshot-v1",
        "generated_at": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": "Asia/Shanghai",
        "standing": True,
        "generated_at_beijing": beijing_clock(current),
        "sources": checks,
        "events": events,
    }


def write_snapshot(path: str, payload: dict):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    try:
        os.chmod(parent, 0o755)
    except PermissionError:
        pass
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)
    os.chmod(path, 0o644)


def _dedupe(projects: list[dict]) -> list[dict]:
    chosen = {}
    for item in projects:
        key = (item["role"], item["name"].casefold())
        current = chosen.get(key)
        if current is None or (not current["url"] and item["url"]):
            chosen[key] = item
    return sorted(chosen.values(), key=lambda item: (item["role"], item["place"], item["name"]))


def _milestone(item) -> dict:
    return {
        "key": item["milestone_key"],
        "label": item["label"],
        "start_utc": item["start_utc"],
        "end_utc": item["end_utc"],
        "display": item["display"],
        "timezone_label": item["timezone_label"],
        "precision": item["precision"],
        "source_url": item["source_url"],
    }


def _project(item) -> dict:
    return {
        "name": item["name"],
        "role": item["role"],
        "place": item["place"],
        "track": item["track"],
        "url": item["url"],
        "source_url": item["source_url"],
        "note": item["note"],
    }
