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
    def __init__(self, path: Path, *, initialize=False):
        from .migration import inspect, migrate, safe_path

        self.path = safe_path(path)
        if initialize:
            migrate(self.path)
        else:
            inspect(self.path)

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

    def insert_tweet(self, row: dict, tweet: dict, source: str) -> bool:
        import uuid

        from .commands import activity, change
        from .protocol import SCOPE, canonical

        source = "rest" if source == "rest_recovery" else source
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.get(row["project_id"], db)
            if current["revision"] != row["revision"] or current["desired"] != "running":
                db.execute("ROLLBACK")
                return False
            created = tweet["created_at"]
            if (created is not None and created < current["generation_at"]) or (
                created is None and source != "wss"
            ):
                db.execute("ROLLBACK")
                return False
            aid = "act_" + str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{current['subscription_id']}:{current['generation']}:{tweet['tweet_id']}",
                )
            )
            prior = db.execute("SELECT 1 FROM tweets WHERE activity_id=?", (aid,)).fetchone()
            changed = (
                db.execute(
                    """INSERT INTO tweets(activity_id,project_id,subscription_id,handle,tweet_id,text,created_at,received_at,source,generation)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(subscription_id,generation,tweet_id) DO UPDATE SET text=excluded.text
                WHERE tweets.text='' AND excluded.text!=''""",
                    (
                        aid,
                        current["project_id"],
                        current["subscription_id"],
                        current["handle"],
                        tweet["tweet_id"],
                        tweet["text"],
                        created,
                        time.time(),
                        source,
                        current["generation"],
                    ),
                ).rowcount
                == 1
            )
            if changed and not prior:
                record = dict(
                    db.execute(
                        "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id) WHERE activity_id=?",
                        (aid,),
                    ).fetchone()
                )
                dto = activity(record)
                eid = change(db, "tracking.activity.created", dto)
                envelope = {
                    "schema_version": 1,
                    "event_id": eid,
                    "source": "tracking",
                    "event_type": "tracking.activity.created",
                    "occurred_at": dto["occurred_at"],
                    "received_at": dto["received_at"],
                    "tenant_id": SCOPE,
                    "project_id": current["project_id"],
                    "correlation_id": aid,
                    "payload": dto,
                }
                db.execute(
                    "INSERT INTO tracking_outbox(event_id,envelope,state,updated_at) VALUES(?,?,?,?)",
                    (eid, canonical(envelope), "pending", time.time()),
                )
            db.execute("COMMIT")
            return changed

    def activities(self, project_id: str | None = None, after: int = 0, limit: int = 50) -> list[dict]:
        with self.connect() as db:
            clauses, args = ["t.seq>?"], [after]
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
            rows = db.execute(
                "SELECT t.*,p.name AS project_name FROM tweets t JOIN projects p USING(project_id)"
                + (" WHERE t.project_id=?" if project_id else "")
                + " ORDER BY t.seq DESC LIMIT ?",
                (project_id, limit) if project_id else (limit,),
            )
            return [{**dict(r), "url": f"https://x.com/{r['handle']}/status/{r['tweet_id']}"} for r in rows]

    def session(self, *args, **kwargs):
        raise ValueError("Human sessions belong exclusively to auth.db")

    def logout(self, *args, **kwargs):
        raise ValueError("Human sessions belong exclusively to auth.db")

    def login_allowed(self, *args, **kwargs):
        raise ValueError("Human login limits belong exclusively to auth.db")
