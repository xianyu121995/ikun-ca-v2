from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

APP_ID = 0x494B0202  # v2 foundation tracking store identity.
HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}\Z")


class Conflict(Exception):
    pass


class Missing(Exception):
    pass


def handle(value: str) -> str:
    value = value.strip().lstrip("@").lower()
    if not HANDLE.fullmatch(value):
        raise ValueError("invalid X handle")
    return value


class Store:
    def __init__(self, path: Path, *, initialize=False, _restoring=False):
        from .migration import inspect, migrate, safe_path

        self.path = safe_path(path)
        if initialize:
            migrate(self.path)
        else:
            inspect(self.path, allow_recovery=_restoring)

    @contextlib.contextmanager
    def connect(self):
        from .migration import safe_path

        path = safe_path(self.path)
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            if db.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
                raise ValueError("tracking database identity changed")
            owner = db.execute("SELECT store_name FROM _store_identity WHERE singleton=1").fetchone()
            if not owner or owner[0] != "tracking":
                raise ValueError("tracking database identity changed")
            if db.execute("PRAGMA user_version").fetchone()[0] != 4 or db.execute(
                "SELECT database_path FROM feed_meta WHERE singleton=1"
            ).fetchone()[0] != str(path):
                raise ValueError("tracking schema or physical identity changed")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    def get(self, project_id: str, db=None) -> dict:
        if db is None:
            with self.connect() as db:
                return self.get(project_id, db)
        row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise Missing(project_id)
        return dict(row)

    def projects(self, include_removed=False) -> list[dict]:
        with self.connect() as db:
            sql = "SELECT * FROM projects" + (
                "" if include_removed else " WHERE desired!='removed' OR status!='removed'"
            )
            return [dict(r) for r in db.execute(sql + " ORDER BY created_at,project_id")]

    def mutate(self, action: str, project_id: str, payload: dict, actor: str, key: str) -> dict:
        key = hashlib.sha256(
            json.dumps([actor, action, "" if action == "create" else project_id, key]).encode()
        ).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps([actor, action, project_id, payload], sort_keys=True).encode()
        ).hexdigest()
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                receipt = db.execute("SELECT * FROM receipts WHERE key=?", (key,)).fetchone()
                if receipt:
                    if receipt["fingerprint"] != fingerprint:
                        raise Conflict("idempotency key already used with different request")
                    db.execute("COMMIT")
                    return json.loads(receipt["result"])
                if action == "create":
                    if payload.get("confirmed") is not True:
                        raise ValueError("explicit human confirmation required")
                    if not re.fullmatch(
                        r"prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", project_id
                    ):
                        raise ValueError("canonical project_id required")
                    if db.execute(
                        "SELECT 1 FROM projects WHERE project_id=? OR handle=?",
                        (project_id, handle(payload["handle"])),
                    ).fetchone():
                        raise Conflict("project or X handle already exists; use resume")
                    db.execute(
                        """INSERT INTO projects(project_id,name,handle,notes,confirmed_by,confirmed_at,
                        desired,generation_at,created_at,updated_at) VALUES(?,?,?,?,?,?,'running',?,?,?)""",
                        (
                            project_id,
                            payload["name"],
                            handle(payload["handle"]),
                            payload.get("notes", ""),
                            actor,
                            now,
                            now,
                            now,
                            now,
                        ),
                    )
                else:
                    row = self.get(project_id, db)
                    if row["revision"] != payload["expected_revision"]:
                        raise Conflict("revision changed; refresh before retry")
                    if action == "update":
                        db.execute(
                            "UPDATE projects SET name=?,notes=?,revision=revision+1,updated_at=? WHERE project_id=?",
                            (
                                payload.get("name", row["name"]),
                                payload.get("notes", row["notes"]),
                                now,
                                project_id,
                            ),
                        )
                    else:
                        desired = {
                            "start": "running",
                            "resume": "running",
                            "stop": "stopped",
                            "remove": "removed",
                        }[action]
                        generation = desired == "running" and row["desired"] != "running"
                        db.execute(
                            """UPDATE projects SET desired=?,status='pending',error=NULL,attempts=0,next_retry=0,
                            revision=revision+1,updated_at=?,generation=generation+?,
                            generation_at=CASE WHEN ? THEN ? ELSE generation_at END,
                            last_backfill=CASE WHEN ? THEN NULL ELSE last_backfill END,
                            coverage=CASE WHEN ? THEN 'pending' ELSE coverage END WHERE project_id=?""",
                            (
                                desired,
                                now,
                                int(generation),
                                generation,
                                now,
                                generation,
                                generation,
                                project_id,
                            ),
                        )
                if action == "create":
                    import uuid

                    db.execute(
                        "UPDATE projects SET subscription_id=? WHERE project_id=?",
                        ("sub_" + str(uuid.uuid4()), project_id),
                    )
                result = self.get(project_id, db)
                db.execute(
                    "INSERT INTO audit(project_id,actor,action,at,detail) VALUES(?,?,?,?,?)",
                    (project_id, actor, action, now, json.dumps({"revision": result["revision"]})),
                )
                db.execute(
                    "INSERT INTO receipts(key,fingerprint,result,at) VALUES(?,?,?,?)",
                    (key, fingerprint, json.dumps(result), now),
                )
                db.execute("COMMIT")
                return result
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def adopt_watch(self, row: dict, watch_id) -> bool:
        """Fence ownership and its audit in one transaction; do not mutate remote flags."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE projects SET claim='owned' WHERE project_id=? AND revision=? AND claim!='owned'", (row['project_id'],row['revision'])).rowcount
            if changed:
                db.execute("INSERT INTO audit(project_id,actor,action,at,detail) VALUES(?,?,?,?,?)", (row['project_id'],'tracking-worker','watch_adopted',time.time(),json.dumps({'handle':row['handle'],'watch_id':str(watch_id),'flags_preserved':True})))
            db.execute("COMMIT")
            return bool(changed)

    def observe(self, row: dict, **changes) -> bool:
        from .commands import change, observed
        from .views import subscription

        allowed = {
            "remote_state",
            "observed_at",
            "claim",
            "status",
            "error",
            "attempts",
            "next_retry",
            "last_backfill",
            "coverage",
            "baseline_ready",
        }
        if not changes or changes.keys() - allowed:
            raise ValueError("invalid observation fields")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            before = self.get(row["project_id"], db)
            updated = (
                db.execute(
                    "UPDATE projects SET "
                    + ",".join(f"{k}=?" for k in changes)
                    + " WHERE project_id=? AND revision=?",
                    (*changes.values(), row["project_id"], row["revision"]),
                ).rowcount
                == 1
            )
            if updated:
                observed(db, before, changes)
                after = self.get(row["project_id"], db)
                if any(before[k] != after[k] for k in ("remote_state", "status", "error")):
                    change(db, "tracking.subscription.updated", subscription(self, after, db=db))
            db.execute("COMMIT")
            return updated

    def runtime(self, **changes) -> dict:
        if changes.keys() - {"worker_id", "heartbeat", "connection", "pong_at", "error"}:
            raise ValueError("invalid runtime fields")
        with self.connect() as db:
            if changes:
                db.execute(
                    "UPDATE runtime SET " + ",".join(f"{k}=?" for k in changes) + " WHERE id=1",
                    tuple(changes.values()),
                )
            return dict(db.execute("SELECT * FROM runtime WHERE id=1").fetchone())

    def lease(self, owner: str, *, acquire=False, release=False) -> bool:
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runtime WHERE id=1").fetchone()
            if acquire:
                accepted = row["worker_id"] == owner or not row["heartbeat"] or row["heartbeat"] < now - 30
                if accepted:
                    db.execute(
                        "UPDATE runtime SET worker_id=?,heartbeat=?,connection='disconnected',pong_at=NULL,error=NULL WHERE id=1",
                        (owner, now),
                    )
                    db.execute(
                        "UPDATE commands SET state='unknown',error_code='UPSTREAM_TIMEOUT',updated_at=? WHERE state='running' AND remote_attempted=1",
                        (now,),
                    )
            elif release:
                accepted = row["worker_id"] == owner
                if accepted:
                    db.execute(
                        "UPDATE runtime SET heartbeat=0,connection='disconnected',pong_at=NULL WHERE id=1"
                    )
            else:
                accepted = row["worker_id"] == owner and row["heartbeat"] and row["heartbeat"] > now - 30
                if accepted:
                    db.execute("UPDATE runtime SET heartbeat=? WHERE id=1", (now,))
            db.execute("COMMIT")
            return bool(accepted)

    def check_retention_clock(self, *, now_ms=None, monotonic_ms=None, acknowledge=False):
        from .retention import retention_now, wall_ms

        now_ms = wall_ms() if now_ms is None else now_ms
        mono = int(time.monotonic() * 1000) if monotonic_ms is None else monotonic_ms
        previous = getattr(self, "_retention_clock", None)
        anomaly = previous is not None and abs((now_ms - previous[0]) - (mono - previous[1])) > 300000
        self._retention_clock = (now_ms, mono)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if anomaly:
                db.execute("UPDATE feed_meta SET clock_anomaly=1 WHERE singleton=1")
            if acknowledge:
                last = db.execute("SELECT last_retention_now_ms FROM feed_meta WHERE singleton=1").fetchone()[
                    0
                ]
                if anomaly or now_ms < last:
                    raise ValueError("clock is not safe to acknowledge")
                db.execute("UPDATE feed_meta SET clock_anomaly=0 WHERE singleton=1")
            now = retention_now(db, now_ms)
            flagged = db.execute("SELECT clock_anomaly FROM feed_meta WHERE singleton=1").fetchone()[0]
            db.execute("COMMIT")
            return {"retention_now_ms": now, "clock_anomaly": bool(flagged)}

    def insert_tweet(self, row: dict, tweet: dict, source: str) -> bool:
        import math
        import uuid

        from .commands import activity, change
        from .feed import activity_id
        from .protocol import SCOPE, canonical
        from .retention import TTL_MS, retention_now

        historical = source in ("adopt_rest_recovery", "adopt_wss_replay")
        source = (
            "rest"
            if source in ("rest_recovery", "adopt_rest_recovery")
            else "wss"
            if source == "adopt_wss_replay"
            else source
        )
        if tweet.get("author_verified") is not True or tweet.get("tweet_kind") not in (
            "original",
            "quote",
            "reply",
            "repost",
            "unknown",
        ):
            return False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.get(row["project_id"], db)
            if (
                current["revision"] != row["revision"]
                or current["desired"] != "running"
                or (current["x_user_id"] and tweet.get("author_id") != current["x_user_id"])
                or tweet.get("author_handle") != current["handle"]
            ):
                db.execute("ROLLBACK")
                return False
            now = retention_now(db)
            created = tweet["created_at"]
            if (
                type(created) not in (int, float)
                or not math.isfinite(created)
                or created <= 0
                or created * 1000 > now
            ):
                created = None
            ledger = db.execute(
                "SELECT * FROM tweet_ledger WHERE tweet_id=?", (tweet["tweet_id"],)
            ).fetchone()
            if (
                ledger
                and created is not None
                and ledger["first_received_at_ms"] is not None
                and created * 1000 > ledger["first_received_at_ms"]
            ):
                created = None
            expiry = min(now, int(round(created * 1000))) + TTL_MS if created is not None else now + TTL_MS
            if ledger:
                expiry = min(expiry, ledger["expires_at_ms"])
            if (
                not ledger
                and expiry > now
                and (
                    (created is not None and created < current["generation_at"])
                    or (created is None and source != "wss")
                )
            ):
                db.execute("COMMIT")
                return False
            first = ledger is None
            if first:
                db.execute(
                    "INSERT INTO tweet_ledger(tweet_id,expires_at_ms,first_received_at_ms,origin_subscription_id,state) VALUES(?,?,?,?,?)",
                    (
                        tweet["tweet_id"],
                        expiry,
                        now,
                        current["subscription_id"],
                        "expired"
                        if expiry <= now
                        else "visible"
                        if tweet["tweet_kind"] in ("original", "quote")
                        else "unknown",
                    ),
                )
                ledger = db.execute(
                    "SELECT * FROM tweet_ledger WHERE tweet_id=?", (tweet["tweet_id"],)
                ).fetchone()
            elif (
                ledger["state"] == "expired" or ledger["origin_subscription_id"] != current["subscription_id"]
            ):
                db.execute("COMMIT")
                return False
            db.execute(
                "UPDATE tweet_ledger SET expires_at_ms=MIN(expires_at_ms,?) WHERE tweet_id=?",
                (expiry, tweet["tweet_id"]),
            )
            db.execute(
                "UPDATE tweets SET expires_at_ms=MIN(expires_at_ms,?) WHERE tweet_id=?",
                (expiry, tweet["tweet_id"]),
            )
            if expiry <= now:
                # Preserve the pending purge marker if older payload still exists.
                if first:
                    db.execute(
                        "UPDATE tweet_ledger SET first_received_at_ms=NULL,origin_subscription_id=NULL WHERE tweet_id=?",
                        (tweet["tweet_id"],),
                    )
                db.execute("COMMIT")
                return False
            aid = "act_" + str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{current['subscription_id']}:{current['generation']}:{tweet['tweet_id']}",
                )
            )
            prior = db.execute("SELECT * FROM tweets WHERE activity_id=?", (aid,)).fetchone()
            known_before = db.execute(
                "SELECT 1 FROM tweets WHERE subscription_id=? AND tweet_id=? AND tweet_kind IN ('original','quote') AND author_verified=1",
                (current["subscription_id"], tweet["tweet_id"]),
            ).fetchone()
            if prior:
                conflicted = "conflicting-structured-v1" in (
                    prior["type_evidence_version"],
                    tweet["type_evidence_version"],
                )
                kind = (
                    "unknown"
                    if conflicted
                    else tweet["tweet_kind"]
                    if prior["tweet_kind"] == "unknown"
                    else prior["tweet_kind"]
                )
                # Conflicting reliable type evidence is hidden, never guessed back to original.
                if (
                    prior["tweet_kind"] != "unknown"
                    and tweet["tweet_kind"] != "unknown"
                    and prior["tweet_kind"] != tweet["tweet_kind"]
                ):
                    kind = "unknown"
                    conflicted = True
                text = prior["text"] or tweet["text"]
                occurred = prior["created_at"] if prior["created_at"] is not None else created
                if occurred is not None and created is not None:
                    occurred = min(occurred, created)
                changed = (
                    text != prior["text"] or occurred != prior["created_at"] or kind != prior["tweet_kind"]
                )
                if changed:
                    db.execute(
                        "UPDATE tweets SET text=?,created_at=?,tweet_kind=?,author_verified=1,type_evidence_version=? WHERE activity_id=?",
                        (
                            text,
                            occurred,
                            kind,
                            "conflicting-structured-v1" if conflicted else tweet["type_evidence_version"],
                            aid,
                        ),
                    )
            else:
                kind = tweet["tweet_kind"]
                changed = True
                db.execute(
                    "INSERT INTO tweets(activity_id,project_id,subscription_id,handle,tweet_id,text,created_at,received_at,source,generation,tweet_kind,author_verified,type_evidence_version,expires_at_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                    (
                        aid,
                        current["project_id"],
                        current["subscription_id"],
                        current["handle"],
                        tweet["tweet_id"],
                        tweet["text"],
                        created,
                        now / 1000,
                        source,
                        current["generation"],
                        kind,
                        tweet["type_evidence_version"],
                        expiry,
                    ),
                )
            context = tweet.get("quoted_tweet")
            if kind == "quote" and isinstance(context, dict):
                # Normalized public context belongs to this DB; no raw frame or new schema.
                from .events import quoted_context
                normalized = quoted_context({"quotedStatus": {"id": context.get("tweet_id"),
                    "text": context.get("text"), "userScreenName": context.get("author_handle"),
                    "userName": context.get("author_name")}})
                if normalized:
                    encoded = canonical(normalized)
                    key = "tracking.quote.v1:" + tweet["tweet_id"]
                    previous = db.execute("SELECT result FROM receipts WHERE key=?", (key,)).fetchone()
                    if previous is None:
                        db.execute("INSERT INTO receipts(key,fingerprint,result,at) VALUES(?,?,?,?)",
                            (key, hashlib.sha256(encoded.encode()).hexdigest(), encoded, time.time()))
                        changed = True
                        db.execute("UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1")
            if changed:
                if kind in ("original", "quote"):
                    db.execute(
                        "UPDATE tweet_ledger SET state='visible' WHERE tweet_id=?", (tweet["tweet_id"],)
                    )
                record = dict(
                    db.execute(
                        "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id) WHERE activity_id=?",
                        (aid,),
                    ).fetchone()
                )
                if first and kind in ("original", "quote") and not historical:
                    change(db, "tracking.activity.created", activity(record))
                versioned = activity(record) | {
                    "activity_id": activity_id(current["subscription_id"], tweet["tweet_id"]),
                    "tweet_kind": kind,
                    "replay": not (
                        first and source == "wss" and kind in ("original", "quote") and not historical
                    ),
                    "is_live_new": bool(
                        first and source == "wss" and kind in ("original", "quote") and not historical
                    ),
                }
                event_type = (
                    "tracking.feed.activity.created.v1"
                    if versioned["is_live_new"]
                    else "tracking.feed.activity.updated.v1"
                )
                if kind in ("original", "quote") or known_before:
                    eid = change(db, event_type, versioned)
                    envelope = {
                        "schema_version": 1,
                        "event_id": eid,
                        "source": "tracking",
                        "event_type": event_type,
                        "occurred_at": versioned["occurred_at"],
                        "received_at": versioned["received_at"],
                        "tenant_id": SCOPE,
                        "project_id": current["project_id"],
                        "correlation_id": versioned["activity_id"],
                        "payload": versioned,
                    }
                    db.execute(
                        "INSERT INTO tracking_outbox(event_id,envelope,state,updated_at) VALUES(?,?,?,?)",
                        (eid, canonical(envelope), "pending", time.time()),
                    )
            db.execute("COMMIT")
            return changed

    def activities(self, project_id: str | None = None, after: int = 0, limit: int = 50) -> list[dict]:
        with self.connect() as db:
            from .retention import retention_now

            clauses, args = (
                [
                    "t.seq>?",
                    "t.expires_at_ms>?",
                    "t.tweet_kind IN ('original','quote')",
                    "t.author_verified=1",
                ],
                [after, retention_now(db)],
            )
            if project_id:
                self.get(project_id, db)
                clauses.append("t.project_id=?")
                args.append(project_id)
            rows = db.execute(
                "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id) WHERE "
                + " AND ".join(clauses)
                + " ORDER BY t.seq LIMIT ?",
                (*args, limit),
            )
            return [{**dict(r), "url": f"https://x.com/{r['handle']}/status/{r['tweet_id']}"} for r in rows]

    def latest_time(self, project_id: str) -> float | None:
        with self.connect() as db:
            return db.execute(
                "SELECT MAX(created_at) FROM tweets WHERE project_id=?", (project_id,)
            ).fetchone()[0]

    def tweet_stats(self, project_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT COUNT(*),MAX(created_at) FROM tweets WHERE project_id=?", (project_id,)
            ).fetchone()
            return {"tweet_count": row[0], "last_tweet_at": row[1]}

    def latest(self, project_id=None, limit=50):
        with self.connect() as db:
            if project_id:
                self.get(project_id, db)
            from .retention import retention_now

            now = retention_now(db)
            rows = db.execute(
                "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id) WHERE t.expires_at_ms>? AND t.author_verified=1 AND t.tweet_kind IN ('original','quote')"
                + (" AND t.project_id=?" if project_id else "")
                + " ORDER BY t.seq DESC LIMIT ?",
                (now, project_id, limit)
                if project_id
                else (
                    now,
                    limit,
                ),
            )
            return [{**dict(r), "url": f"https://x.com/{r['handle']}/status/{r['tweet_id']}"} for r in rows]

    def session(self, *args, **kwargs):
        raise ValueError("Human sessions belong exclusively to auth.db")

    def logout(self, *args, **kwargs):
        raise ValueError("Human sessions belong exclusively to auth.db")

    def login_allowed(self, *args, **kwargs):
        raise ValueError("Human login limits belong exclusively to auth.db")
