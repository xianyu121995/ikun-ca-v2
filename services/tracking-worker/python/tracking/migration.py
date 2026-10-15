"""Explicit migrations for this physical tracking.db only. Runtime opens are read-only validation."""

import hashlib
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .protocol import UUID4

APP_ID = 0x494B0202
SCHEMAS = Path(__file__).resolve().parents[4] / "schemas/tracking"

REQUIRED_COLUMNS = {
    "projects": "project_id name handle notes confirmed_by confirmed_at desired remote_state observed_at claim status error attempts next_retry revision generation generation_at last_backfill coverage created_at updated_at subscription_id x_user_id active_command_id baseline_ready",
    "tweets": "seq activity_id project_id subscription_id handle tweet_id text created_at received_at source generation",
    "commands": "command_id body_hash envelope project_id subscription_id revision state error_code created_at updated_at request_id remote_attempted",
    "public_receipts": "actor_id route key body_hash response created_at",
    "changes": "seq event_id event_type data received_at",
    "tracking_outbox": "event_id envelope state error_code receipt updated_at",
    "runtime": "id worker_id heartbeat connection pong_at error",
    "audit": "seq project_id actor action at detail",
    "receipts": "key fingerprint result at",
    "tweets_legacy": "seq project_id handle tweet_id text created_at received_at source generation",
}


def ledger(db):
    columns = {r[1] for r in db.execute("PRAGMA table_info(_schema_migrations)")}
    if columns not in (
        {"version", "name", "applied_at"},
        {"version", "name", "applied_at", "checksum"},
    ):
        raise ValueError("unsupported ledger")
    names = {1: {"foundation"}, 2: {"tracking_v2", "tracking_new_tweet_v1"}, 3: {"tracking_v3"}}
    rows = db.execute("SELECT version,name FROM _schema_migrations").fetchall()
    for version, name in rows:
        if version not in names:
            raise ValueError("unsupported future schema")
        if name not in names[version]:
            raise ValueError("tracking migration name mismatch")
    return {r[0] for r in rows}, columns


def structure(db):
    for table, required in REQUIRED_COLUMNS.items():
        columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        if not set(required.split()) <= columns:
            raise ValueError("tracking schema structure mismatch")
    for table, required in {
        "projects": {("project_id",), ("handle",), ("subscription_id",), ("x_user_id",)},
        "tweets": {("activity_id",), ("subscription_id", "generation", "tweet_id")},
        "commands": {("command_id",)},
        "changes": {("event_id",)},
    }.items():
        unique = {
            tuple(c[2] for c in db.execute("SELECT * FROM pragma_index_info(?)", (r[1],)))
            for r in db.execute(f"PRAGMA index_list({table})")
            if r[2]
        }
        if not required <= unique:
            raise ValueError("tracking schema uniqueness mismatch")


def safe_path(path, *, create=False):
    path = Path(path).absolute()
    if path.name != "tracking.db" or path.parent.name != "tracking" or path != path.resolve():
        raise ValueError("only nonaliased tracking.db is allowed")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.is_symlink() or (p.exists() and p.stat().st_nlink != 1):
            raise ValueError("database path alias rejected")
    if create:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    return path


def hashes():
    return {
        v: hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest()
        for v, name in [(1, "001_foundation.sql"), (2, "002_tracking.sql"), (3, "003_commands.sql")]
    }


def inspect(path, *, maximum=3):
    path = safe_path(path)
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        if db.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
            raise ValueError("foreign database rejected")
        if db.execute("SELECT store_name FROM _store_identity WHERE singleton=1").fetchone() != ("tracking",):
            raise ValueError("store owner mismatch")
        versions, _ = ledger(db)
        if (
            not versions
            or max(versions) > maximum
            or db.execute("PRAGMA user_version").fetchone()[0] > maximum
        ):
            raise ValueError("unsupported future schema")
        if maximum == 3 and set(versions) != {1, 2, 3}:
            raise ValueError("explicit tracking migrate required")
        if maximum == 3 and db.execute("PRAGMA user_version").fetchone()[0] != 3:
            raise ValueError("tracking schema version mismatch")
        expected = hashes()
        for version, digest in db.execute("SELECT version,sha256 FROM _migration_checksums"):
            allowed = {expected.get(version)}
            if version == 2:
                allowed.add(hashlib.sha256((SCHEMAS / "002_legacy_reference.sql").read_bytes()).hexdigest())
            if digest not in allowed:
                raise ValueError("tracking migration checksum mismatch")
        if set(r[0] for r in db.execute("SELECT version FROM _migration_checksums")) != set(versions):
            raise ValueError("missing migration checksum")
        if maximum == 3:
            structure(db)
    finally:
        db.close()


def migrate(path, *, fault=None):
    path = safe_path(path, create=True)
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    expected = hashes()
    try:
        marker = db.execute("PRAGMA application_id").fetchone()[0]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if marker not in (0, APP_ID) or (marker == 0 and tables):
            raise ValueError("foreign database rejected")
        if marker == APP_ID and not {"_store_identity", "_schema_migrations"} <= tables:
            raise ValueError("tracking schema structure mismatch")
        if db.execute("PRAGMA user_version").fetchone()[0] > 3:
            raise ValueError("unsupported future schema")
        if "_store_identity" in tables:
            row = db.execute("SELECT store_name FROM _store_identity WHERE singleton=1").fetchone()
            if not row or row[0] != "tracking":
                raise ValueError("store owner mismatch")
        if "_schema_migrations" in tables:
            versions, columns = ledger(db)
            if versions not in ({1}, {2}, {1, 2}, {1, 2, 3}):
                raise ValueError("tracking migration history mismatch")
            if "checksum" in columns:
                legacy = db.execute("SELECT checksum FROM _schema_migrations WHERE version=2").fetchone()
                allowed = {
                    expected[2],
                    hashlib.sha256((SCHEMAS / "002_legacy_reference.sql").read_bytes()).hexdigest(),
                }
                if legacy and legacy[0] is not None and legacy[0] not in allowed:
                    raise ValueError("tracking migration checksum mismatch")
                if legacy and legacy[0] is None:
                    registered = (
                        db.execute("SELECT sha256 FROM _migration_checksums WHERE version=2").fetchone()
                        if "_migration_checksums" in tables
                        else None
                    )
                    if not registered or registered[0] not in allowed:
                        raise ValueError("missing legacy migration checksum")
        else:
            versions = set()
        if "_migration_checksums" in tables:
            for v, d in db.execute("SELECT version,sha256 FROM _migration_checksums"):
                allowed = {expected.get(v)}
                if v == 2:
                    allowed.add(
                        hashlib.sha256((SCHEMAS / "002_legacy_reference.sql").read_bytes()).hexdigest()
                    )
                if d not in allowed:
                    raise ValueError("tracking migration checksum mismatch")
        for name in ("sessions", "login_limits"):
            if name in tables and db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]:
                raise ValueError("legacy human identity retirement requires explicit review")
        if 3 in versions:
            inspect(path)
            return
        if 2 in versions:
            for project_id, generation in db.execute("SELECT project_id,generation FROM projects"):
                if (
                    not re.fullmatch("prj_" + UUID4, project_id)
                    or type(generation) is not int
                    or generation < 1
                ):
                    raise ValueError("legacy project mapping requires explicit review")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        for version, name in [(1, "001_foundation.sql"), (2, "002_tracking.sql"), (3, "003_commands.sql")]:
            if version not in versions:
                # executescript would implicitly commit. Execute complete statements in this one transaction.
                sql = (SCHEMAS / name).read_text()
                for statement in sql.split(";"):
                    if statement.strip():
                        db.execute(statement)
                if version == 1:
                    db.execute(
                        "INSERT OR IGNORE INTO _store_identity(singleton,store_name) VALUES(1,'tracking')"
                    )
                if version == 2:
                    db.execute("INSERT OR IGNORE INTO runtime(id) VALUES(1)")
                if version == 3:
                    for row in db.execute("SELECT project_id FROM projects").fetchall():
                        db.execute(
                            "UPDATE projects SET subscription_id=? WHERE project_id=?",
                            ("sub_" + str(uuid.uuid4()), row[0]),
                        )
                    for row in db.execute(
                        "SELECT t.*,p.subscription_id FROM tweets_legacy t JOIN projects p USING(project_id)"
                    ).fetchall():
                        db.execute(
                            """INSERT INTO tweets(seq,activity_id,project_id,subscription_id,handle,tweet_id,text,created_at,received_at,source,generation)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                row["seq"],
                                "act_"
                                + str(
                                    uuid.uuid5(
                                        uuid.NAMESPACE_URL,
                                        f"{row['subscription_id']}:{row['generation']}:{row['tweet_id']}",
                                    )
                                ),
                                row["project_id"],
                                row["subscription_id"],
                                row["handle"],
                                row["tweet_id"],
                                row["text"],
                                row["created_at"],
                                row["received_at"],
                                "rest" if row["source"] == "rest_recovery" else row["source"],
                                row["generation"],
                            ),
                        )
                db.execute(
                    "INSERT INTO _schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                    (
                        version,
                        "foundation" if version == 1 else f"tracking_v{version}",
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    ),
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL)"
            )
            digest = expected[version]
            if (
                version == 2
                and version in versions
                and "checksum" in {r[1] for r in db.execute("PRAGMA table_info(_schema_migrations)")}
            ):
                row = db.execute("SELECT checksum FROM _schema_migrations WHERE version=2").fetchone()
                if row and row[0]:
                    digest = row[0]
            db.execute(
                "INSERT OR IGNORE INTO _migration_checksums(version,sha256) VALUES(?,?)", (version, digest)
            )
            if fault == version:
                raise RuntimeError("injected migration failure")
        db.execute(f"PRAGMA application_id={APP_ID}")
        db.execute("PRAGMA user_version=3")
        db.execute("COMMIT")
        os.chmod(path, 0o600)
        os.chmod(path.parent, 0o700)
    finally:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
    inspect(path)
