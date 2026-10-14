from __future__ import annotations

import contextlib
import hashlib
import json
import os
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
    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        if self.path.name != "tracking.db":
            raise ValueError("only tracking.db may be opened")
        if self.path != self.path.resolve():
            raise ValueError("symlink database paths are forbidden")
        if any(Path(str(self.path) + suffix).is_symlink() for suffix in ("-wal", "-shm")):
            raise ValueError("symlink database sidecars are forbidden")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # O_NOFOLLOW also closes the final-component symlink race.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_nlink != 1:
                raise ValueError("hardlinked databases are forbidden")
        finally:
            os.close(fd)
        with self.connect() as db:
            identity = db.execute("PRAGMA application_id").fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if identity not in (0, APP_ID) or (identity == 0 and tables):
                raise ValueError("foreign database rejected")
            db.execute(f"PRAGMA application_id={APP_ID}")
            db.execute("PRAGMA journal_mode=WAL")
            schema = Path(__file__).with_name("schema.sql").read_text()
            checksum = hashlib.sha256(schema.encode()).hexdigest()
            names = {r[0] for r in tables}
            if "_store_identity" in names:
                owner = db.execute("SELECT store_name FROM _store_identity WHERE singleton=1").fetchone()
                if not owner or owner[0] != "tracking":
                    raise ValueError("tracking store owner mismatch")
            if "_schema_migrations" in names:
                columns = {r[1] for r in db.execute("PRAGMA table_info(_schema_migrations)")}
                if "checksum" in columns:
                    prior = db.execute("SELECT checksum FROM _schema_migrations WHERE version=2").fetchone()
                    if prior and prior[0] != checksum:
                        raise ValueError("tracking migration checksum mismatch")
            db.executescript("BEGIN IMMEDIATE;\n" + schema)
            columns = {r[1] for r in db.execute("PRAGMA table_info(_schema_migrations)")}
            if "checksum" not in columns:
                db.execute("ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT")
            db.execute("INSERT OR IGNORE INTO _store_identity VALUES(1,'tracking')")
            db.execute(
                "INSERT OR IGNORE INTO _schema_migrations VALUES(2,'tracking_new_tweet_v1',datetime('now'),?)",
                (checksum,),
            )
            db.execute("PRAGMA user_version=2")
            db.execute("COMMIT")

    @contextlib.contextmanager
    def connect(self):
        if self.path.is_symlink() or self.path.stat().st_nlink != 1:
            raise ValueError("unsafe database path")
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        try:
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
                result = self.get(project_id, db)
                db.execute(
                    "INSERT INTO audit(project_id,actor,action,at,detail) VALUES(?,?,?,?,?)",
                    (project_id, actor, action, now, json.dumps({"revision": result["revision"]})),
                )
                db.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?)", (key, fingerprint, json.dumps(result), now)
                )
                db.execute("COMMIT")
                return result
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def observe(self, row: dict, **changes) -> bool:
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
        }
        if not changes or changes.keys() - allowed:
            raise ValueError("invalid observation fields")
        with self.connect() as db:
            return (
                db.execute(
                    "UPDATE projects SET "
                    + ",".join(f"{k}=?" for k in changes)
                    + " WHERE project_id=? AND revision=?",
                    (*changes.values(), row["project_id"], row["revision"]),
                ).rowcount
                == 1
            )

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
        with self.connect() as db:
            # Recheck the command revision within the write transaction; no post-stop events can leak in.
            db.execute("BEGIN IMMEDIATE")
            current = self.get(row["project_id"], db)
            if current["revision"] != row["revision"] or current["desired"] != "running":
                db.execute("ROLLBACK")
                return False
            if tweet["created_at"] < current["generation_at"]:
                db.execute("ROLLBACK")
                return False
            result = db.execute(
                """INSERT INTO tweets(project_id,handle,tweet_id,text,created_at,received_at,source,generation)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(handle,tweet_id) DO UPDATE SET text=excluded.text
                WHERE tweets.text='' AND excluded.text!=''""",
                (
                    row["project_id"],
                    row["handle"],
                    tweet["tweet_id"],
                    tweet["text"],
                    tweet["created_at"],
                    time.time(),
                    source,
                    current["generation"],
                ),
            )
            db.execute("COMMIT")
            return result.rowcount == 1

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

    def session(self, token: str, role: str | None = None):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            if role:
                db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
                db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest, role, time.time() + 3600))
                return role
            row = db.execute(
                "SELECT role FROM sessions WHERE digest=? AND expires>?", (digest, time.time())
            ).fetchone()
            return row[0] if row else None

    def logout(self, token: str):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def login_allowed(self, identity: str) -> bool:
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_limits WHERE window_at<?", (now - 600,))
            db.execute(
                """INSERT INTO login_limits VALUES(?,?,1) ON CONFLICT(identity)
                DO UPDATE SET attempts=attempts+1""",
                (identity, now),
            )
            count = db.execute("SELECT attempts FROM login_limits WHERE identity=?", (identity,)).fetchone()[
                0
            ]
            db.execute("COMMIT")
            return count <= 10
