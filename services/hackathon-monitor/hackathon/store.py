"""Isolated SQLite store. Other services' databases are never opened."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from .model import EventDraft, Link, Milestone, Project

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    classification TEXT NOT NULL,
    classification_reason TEXT NOT NULL,
    summary TEXT NOT NULL,
    location TEXT NOT NULL,
    prize TEXT NOT NULL,
    official_status TEXT,
    start_utc TEXT,
    end_utc TEXT,
    submission_state TEXT NOT NULL,
    submission_note TEXT NOT NULL,
    submission_form_url TEXT,
    results_state TEXT NOT NULL,
    results_note TEXT NOT NULL,
    listed INTEGER NOT NULL DEFAULT 1,
    missing_note TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    ecosystem TEXT NOT NULL DEFAULT 'bnb'
);
CREATE TABLE IF NOT EXISTS milestones (
    event_id TEXT NOT NULL,
    milestone_key TEXT NOT NULL,
    label TEXT NOT NULL,
    start_utc TEXT,
    end_utc TEXT,
    display TEXT NOT NULL,
    timezone_label TEXT NOT NULL,
    precision TEXT NOT NULL,
    source_url TEXT NOT NULL,
    PRIMARY KEY (event_id, milestone_key)
);
CREATE TABLE IF NOT EXISTS projects (
    event_id TEXT NOT NULL,
    project_key TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    place TEXT NOT NULL,
    track TEXT NOT NULL,
    url TEXT NOT NULL,
    source_url TEXT NOT NULL,
    note TEXT NOT NULL,
    PRIMARY KEY (event_id, project_key)
);
CREATE TABLE IF NOT EXISTS links (
    event_id TEXT NOT NULL,
    url TEXT NOT NULL,
    label TEXT NOT NULL,
    PRIMARY KEY (event_id, url)
);
CREATE TABLE IF NOT EXISTS source_checks (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    ok INTEGER NOT NULL,
    checked_at TEXT NOT NULL,
    error TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: str):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        try:
            os.chmod(parent, 0o755)
        except PermissionError:
            pass
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(events)")}
        if "ecosystem" not in columns:
            self.db.execute("ALTER TABLE events ADD COLUMN ecosystem TEXT NOT NULL DEFAULT 'bnb'")
        self.db.commit()
        os.chmod(path, 0o600)

    def close(self):
        self.db.close()

    def upsert(self, draft: EventDraft, now: datetime | None = None, replace_projects: bool = True, project_sources: set[str] | None = None, replace_all_projects: bool = False):
        stamp = _now(now)
        with self.db:
            row = self.db.execute(
                "SELECT first_seen, prize, summary, results_state, results_note, submission_state, submission_note, submission_form_url FROM events WHERE id=?",
                (draft.id,),
            ).fetchone()
            prize = draft.prize or (row["prize"] if row else "")
            summary = draft.summary or (row["summary"] if row else "")
            results_state = draft.results_state if draft.touch_results or row is None else row["results_state"]
            results_note = draft.results_note if draft.touch_results or row is None else row["results_note"]
            submission_state = draft.submission_state if draft.touch_submission or row is None else row["submission_state"]
            submission_note = draft.submission_note if draft.touch_submission or row is None else row["submission_note"]
            submission_form = draft.submission_form_url if draft.touch_submission or row is None else row["submission_form_url"]
            self.db.execute(
                """
                INSERT INTO events (
                    id, title, classification, classification_reason, summary, location, prize,
                    official_status, start_utc, end_utc, submission_state, submission_note,
                    submission_form_url, results_state, results_note, listed, missing_note,
                    first_seen, last_seen, ecosystem
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'',?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    classification=excluded.classification,
                    classification_reason=excluded.classification_reason,
                    ecosystem=excluded.ecosystem,
                    summary=excluded.summary,
                    location=CASE WHEN excluded.location!='' THEN excluded.location ELSE events.location END,
                    prize=excluded.prize,
                    official_status=excluded.official_status,
                    start_utc=COALESCE(excluded.start_utc, events.start_utc),
                    end_utc=COALESCE(excluded.end_utc, events.end_utc),
                    submission_state=excluded.submission_state,
                    submission_note=excluded.submission_note,
                    submission_form_url=excluded.submission_form_url,
                    results_state=excluded.results_state,
                    results_note=excluded.results_note,
                    listed=1,
                    missing_note='',
                    last_seen=excluded.last_seen
                """,
                (
                    draft.id, draft.title, draft.classification, draft.classification_reason, summary,
                    draft.location, prize, draft.official_status, draft.start_utc, draft.end_utc,
                    submission_state, submission_note, submission_form,
                    results_state, results_note, row["first_seen"] if row else stamp, stamp, draft.ecosystem,
                ),
            )
            sources = draft.milestone_sources()
            if sources:
                self.db.execute(
                    f"DELETE FROM milestones WHERE event_id=? AND source_url IN ({','.join('?' for _ in sources)})",
                    (draft.id, *sources),
                )
            for item in draft.milestones:
                self.db.execute(
                    """
                    INSERT INTO milestones (
                        event_id, milestone_key, label, start_utc, end_utc, display, timezone_label, precision, source_url
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(event_id, milestone_key) DO UPDATE SET
                        label=excluded.label, start_utc=excluded.start_utc, end_utc=excluded.end_utc,
                        display=excluded.display, timezone_label=excluded.timezone_label,
                        precision=excluded.precision, source_url=excluded.source_url
                    """,
                    (draft.id, item.key, item.label, item.start_utc, item.end_utc, item.display, item.timezone_label, item.precision, item.source_url),
                )
            if replace_all_projects:
                self.db.execute("DELETE FROM projects WHERE event_id=?", (draft.id,))
            spoken = set(project_sources or [])
            if replace_projects and spoken and not replace_all_projects:
                self.db.execute(
                    f"DELETE FROM projects WHERE event_id=? AND source_url IN ({','.join('?' for _ in spoken)})",
                    (draft.id, *spoken),
                )
            if replace_projects or draft.projects:
                for item in draft.projects:
                    self.db.execute(
                        """
                        INSERT INTO projects (
                            event_id, project_key, name, role, place, track, url, source_url, note
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(event_id, project_key) DO UPDATE SET
                            name=excluded.name, role=excluded.role, place=excluded.place, track=excluded.track,
                            url=excluded.url, source_url=excluded.source_url, note=excluded.note
                        """,
                        (draft.id, item.key, item.name, item.role, item.place, item.track, item.url, item.source_url, item.note),
                    )
            for link in draft.links:
                self.db.execute(
                    """
                    INSERT INTO links (event_id, url, label) VALUES (?,?,?)
                    ON CONFLICT(event_id, url) DO UPDATE SET label=excluded.label
                    """,
                    (draft.id, link.url, link.label),
                )

    def replace_source_projects(self, event_id: str, source_url: str, projects: list[Project], results_note: str, now: datetime | None = None):
        stamp = _now(now)
        with self.db:
            self.db.execute(
                "UPDATE events SET results_state=?, results_note=?, last_seen=? WHERE id=?",
                ("published" if projects else "not_published", results_note, stamp, event_id),
            )
            self.db.execute("DELETE FROM projects WHERE event_id=? AND source_url=?", (event_id, source_url))
            for item in projects:
                self.db.execute(
                    """
                    INSERT INTO projects (
                        event_id, project_key, name, role, place, track, url, source_url, note
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (event_id, item.key, item.name, item.role, item.place, item.track, item.url, source_url, item.note),
                )
            self.db.execute(
                "INSERT INTO links (event_id, url, label) VALUES (?,?,?) ON CONFLICT(event_id, url) DO UPDATE SET label=excluded.label",
                (event_id, source_url, "官方结果"),
            )

    def add_link(self, event_id: str, url: str, label: str):
        with self.db:
            self.db.execute(
                """
                INSERT INTO links (event_id, url, label) VALUES (?,?,?)
                ON CONFLICT(event_id, url) DO UPDATE SET label=excluded.label
                """,
                (event_id, url, label),
            )

    def forget_duplicate(self, event_id: str):
        """Drop a blog card that is the same official event as a catalog record."""
        if not event_id.startswith("bnb-blog:"):
            return
        with self.db:
            for table in ("milestones", "projects", "links"):
                self.db.execute(f"DELETE FROM {table} WHERE event_id=?", (event_id,))
            self.db.execute("DELETE FROM events WHERE id=?", (event_id,))

    def mark_index(self, present_ids: set[str], now: datetime | None = None, prefix: str = "bnb-hackathon:", missing_note: str = "官方黑客松目录这次没有再列出它。上次核实的内容仍保留在归档里。"):
        """Keep events that left an official index. Absence is not deletion."""
        stamp = _now(now)
        with self.db:
            rows = self.db.execute("SELECT id FROM events WHERE id LIKE ?", (prefix + "%",)).fetchall()
            for row in rows:
                if row["id"] in present_ids:
                    self.db.execute("UPDATE events SET listed=1, missing_note='', last_seen=? WHERE id=?", (stamp, row["id"]))
                else:
                    self.db.execute("UPDATE events SET listed=0, missing_note=? WHERE id=?", (missing_note, row["id"]))

    def record_source(self, source_id: str, url: str, ok: bool, error: str, note: str, now: datetime | None = None):
        with self.db:
            self.db.execute(
                """
                INSERT INTO source_checks (source_id, url, ok, checked_at, error, note)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET
                    url=excluded.url, ok=excluded.ok, checked_at=excluded.checked_at,
                    error=excluded.error, note=excluded.note
                """,
                (source_id, url, 1 if ok else 0, _now(now), error[:300], note[:300]),
            )

    def set_meta(self, key: str, value: str):
        with self.db:
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def events(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM events ORDER BY COALESCE(start_utc, first_seen)").fetchall()

    def milestones(self, event_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM milestones WHERE event_id=? ORDER BY COALESCE(start_utc, milestone_key)",
            (event_id,),
        ).fetchall()

    def projects(self, event_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM projects WHERE event_id=? ORDER BY role, place, name",
            (event_id,),
        ).fetchall()

    def links(self, event_id: str) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM links WHERE event_id=? ORDER BY label", (event_id,)).fetchall()

    def sources(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM source_checks ORDER BY source_id").fetchall()
