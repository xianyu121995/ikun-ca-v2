"""SQLite-backed memory of what has already been seen.

Two tables:
  obs    - last known value per (source, key), used for diffing
  events - every alert we have emitted, deduped by a content hash
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS obs (
    source     TEXT NOT NULL,
    key        TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    value      TEXT,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    PRIMARY KEY (source, key)
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,
    source     TEXT NOT NULL,
    key        TEXT NOT NULL,
    kind       TEXT NOT NULL,
    level      TEXT NOT NULL,
    title      TEXT NOT NULL,
    detail     TEXT,
    url        TEXT,
    payload    TEXT,
    dedupe     TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,
    payload    TEXT NOT NULL,
    tries      INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts DESC);
"""


def value_hash(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class State:
    def __init__(self, path="radar.sqlite3"):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        self.db.commit()
        self._lock = threading.RLock()

    def _write(self, sql, params=()):
        with self._lock:
            self.db.execute(sql, params)
            self.db.commit()

    # ---------------------------------------------------------------- obs
    def get(self, source, key):
        with self._lock:
            row = self.db.execute(
                "SELECT value FROM obs WHERE source=? AND key=?", (source, key)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def list_keys(self, source):
        with self._lock:
            rows = self.db.execute("SELECT key FROM obs WHERE source=?", (source,)).fetchall()
        return [row["key"] for row in rows]

    def forget(self, source, key):
        self._write("DELETE FROM obs WHERE source=? AND key=?", (source, key))

    def observe(self, source, key, value):
        """Store value; return ('new'|'changed'|'same', old_value)."""
        h = value_hash(value)
        now = int(time.time())
        with self._lock:
            row = self.db.execute(
                "SELECT value_hash, value FROM obs WHERE source=? AND key=?", (source, key)
            ).fetchone()
            if row is None:
                state = "new"
            elif row["value_hash"] != h:
                state = "changed"
            else:
                state = "same"

            if state == "same":
                self.db.execute(
                    "UPDATE obs SET last_seen=? WHERE source=? AND key=?", (now, source, key)
                )
            else:
                self.db.execute(
                    "INSERT INTO obs (source,key,value_hash,value,first_seen,last_seen)"
                    " VALUES (?,?,?,?,?,?)"
                    " ON CONFLICT(source,key) DO UPDATE SET"
                    " value_hash=excluded.value_hash, value=excluded.value, last_seen=excluded.last_seen",
                    (source, key, h, json.dumps(value, ensure_ascii=False, default=str), now, now),
                )
            self.db.commit()
            old = json.loads(row["value"]) if row else None
        return state, old

    # ------------------------------------------------------------- events
    def emit(self, signal):
        """Persist an alert. Returns the row id, or None when it is a duplicate."""
        dedupe = value_hash(
            [signal.source, signal.key, signal.kind, getattr(signal, "fingerprint", None)]
        )
        try:
            with self._lock:
                cur = self.db.execute(
                "INSERT INTO events (ts,source,key,kind,level,title,detail,url,payload,dedupe)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    int(time.time()),
                    signal.source,
                    signal.key,
                    signal.kind,
                    signal.level,
                    signal.title,
                    signal.detail,
                    signal.url,
                    json.dumps(signal.payload, ensure_ascii=False, default=str),
                    dedupe,
                ),
                )
                self.db.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def recent_events(self, limit=20):
        with self._lock:
            return self.db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

    def events_after(self, after_id, limit=50):
        with self._lock:
            return self.db.execute(
                "SELECT * FROM events WHERE id>? ORDER BY id ASC LIMIT ?",
                (int(after_id), int(limit)),
            ).fetchall()

    def max_event_id(self):
        with self._lock:
            row = self.db.execute("SELECT COALESCE(MAX(id),0) AS n FROM events").fetchone()
        return int(row["n"])

    # --------------------------------------------------------------- meta
    def get_meta(self, key, default=None):
        with self._lock:
            row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        self._write(
            "INSERT INTO meta (key,value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def close(self):
        with self._lock:
            self.db.close()

    # ------------------------------------------------------------- outbox
    def queue_alert(self, payload):
        """Persist an undelivered alert so it survives a crash / outage."""
        self._write(
            "INSERT INTO outbox (ts, payload) VALUES (?,?)",
            (int(time.time()), json.dumps(payload, ensure_ascii=False, default=str)),
        )

    def pending_alerts(self, limit=20):
        with self._lock:
            return self.db.execute(
                "SELECT * FROM outbox ORDER BY id LIMIT ?", (limit,)
            ).fetchall()

    def drop_alert(self, row_id):
        self._write("DELETE FROM outbox WHERE id=?", (row_id,))

    def bump_alert(self, row_id, error):
        self._write(
            "UPDATE outbox SET tries=tries+1, last_error=? WHERE id=?",
            (str(error)[:300], row_id),
        )

    def outbox_size(self):
        with self._lock:
            row = self.db.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()
        return row["n"]

    def count_events_since(self, ts):
        with self._lock:
            row = self.db.execute(
                "SELECT COUNT(*) AS n FROM events WHERE ts>=?", (ts,)
            ).fetchone()
        return row["n"]
