"""Bounded, verified local backups and retention. Never opens another domain's database."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .protocol import canonical

TTL_MS = 15 * 86400 * 1000
MAX_BACKUP_BYTES = 1024**3


@contextmanager
def connection(*args, **kwargs):
    db = sqlite3.connect(*args, **kwargs)
    try:
        yield db
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def wall_ms():
    return int(time.time() * 1000)


def retention_now(db, now_ms=None):
    now_ms = wall_ms() if now_ms is None else now_ms
    cursor = db.execute(
        "UPDATE feed_meta SET last_retention_now_ms=MAX(last_retention_now_ms,?) WHERE singleton=1 RETURNING last_retention_now_ms",
        (now_ms,),
    )
    value = cursor.fetchone()[0]
    cursor.close()
    return value


def guard_path(path):
    path = Path(path).absolute()
    if path != path.resolve() or path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
        raise ValueError("backup alias rejected")
    return path


def fsync(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_info(directory):
    directory = guard_path(directory)
    if directory.parent.name != "backups" or directory.parent.parent.name != "tracking":
        raise ValueError("backup must stay in tracking namespace")
    manifest_path = guard_path(directory / "manifest.json")
    path = guard_path(directory / "tracking.db")
    manifest = json.loads(manifest_path.read_text())
    if set(manifest) != {
        "schema_version",
        "policy",
        "created_at_ms",
        "sha256",
        "ledger_high_water",
        "ledger_digest",
        "ledger_count",
    }:
        raise ValueError("invalid backup manifest")
    if file_hash(path) != manifest["sha256"]:
        raise ValueError("backup hash mismatch")
    with connection(path.as_uri() + "?mode=ro", uri=True) as db:
        from .migration import APP_ID, hashes

        if db.execute("PRAGMA application_id").fetchone()[0] != APP_ID or db.execute(
            "SELECT store_name FROM _store_identity WHERE singleton=1"
        ).fetchone() != ("tracking",):
            raise ValueError("backup identity mismatch")
        if (
            db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("backup integrity failure")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version != manifest["schema_version"] or version not in (3, 4):
            raise ValueError("backup schema mismatch")
        expected = hashes()
        checks = dict(db.execute("SELECT version,sha256 FROM _migration_checksums"))
        for v, h in checks.items():
            allowed = {expected.get(v)}
            if v == 2:
                from .migration import SCHEMAS

                allowed.add(hashlib.sha256((SCHEMAS / "002_legacy_reference.sql").read_bytes()).hexdigest())
            if h not in allowed:
                raise ValueError("backup migration checksum mismatch")
        if set(checks) != set(range(1, version + 1)):
            raise ValueError("backup migration history mismatch")
        rows = (
            db.execute(
                "SELECT first_seq,tweet_id,expires_at_ms,state FROM tweet_ledger ORDER BY first_seq"
            ).fetchall()
            if version == 4
            else []
        )
        digest = hashlib.sha256(canonical(rows).encode()).hexdigest()
        if (
            digest != manifest["ledger_digest"]
            or len(rows) != manifest["ledger_count"]
            or max((r[0] for r in rows), default=0) != manifest["ledger_high_water"]
        ):
            raise ValueError("backup ledger watermark mismatch")
    return manifest


def _backups(path):
    directory = guard_path(path.parent / "backups")
    if not directory.exists():
        return []
    result = []
    for entry in directory.iterdir():
        guard_path(entry)
        if entry.is_dir() and (entry / "manifest.json").is_file():
            result.append((entry, backup_info(entry)))
    return sorted(result, key=lambda pair: pair[1]["created_at_ms"])


def prune_backups(path, now_ms, *, preserve_latest=False):
    rows = _backups(path)
    for i, (directory, manifest) in enumerate(rows):
        if preserve_latest and i == len(rows) - 1:
            continue
        if len(rows) - i > 2 or manifest["created_at_ms"] < now_ms - 86400000:
            shutil.rmtree(directory)


def backup_database(path, *, job_id=None, now_ms=None, cancel=None):
    from .migration import safe_path

    path = safe_path(path)
    now_ms = wall_ms() if now_ms is None else now_ms
    prune_backups(path, now_ms, preserve_latest=True)
    parent = guard_path(path.parent / "backups")
    parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(parent, 0o700)
    existing = sum(file.stat().st_size for file in parent.rglob("*") if file.is_file())
    with connection(path.as_uri() + "?mode=ro", uri=True) as db:
        estimate = (
            db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
        )
    if existing + estimate > MAX_BACKUP_BYTES or shutil.disk_usage(parent).free < estimate + 1048576:
        raise OSError("backup capacity exhausted")
    job_id = job_id or "bak_" + str(uuid.uuid4())
    if not job_id.startswith(("bak_", "ret_", "migration_")) or "/" in job_id or ".." in job_id:
        raise ValueError("invalid backup job")
    directory = guard_path(parent / job_id)
    directory.mkdir(mode=0o700)
    target = directory / "tracking.db"
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)

    def progress(status, remaining, total):
        if cancel and cancel():
            raise RuntimeError("backup cancelled")

    try:
        with (
            connection(path.as_uri() + "?mode=ro", uri=True, timeout=5) as source,
            connection(target) as dest,
        ):
            source.backup(dest, pages=256, progress=progress, sleep=0.01)
        os.chmod(target, 0o600)
        with connection(target.as_uri() + "?mode=ro", uri=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            rows = (
                db.execute(
                    "SELECT first_seq,tweet_id,expires_at_ms,state FROM tweet_ledger ORDER BY first_seq"
                ).fetchall()
                if version == 4
                else []
            )
        manifest = {
            "schema_version": version,
            "policy": "product-decisions-v1.1",
            "created_at_ms": now_ms,
            "sha256": file_hash(target),
            "ledger_high_water": max((r[0] for r in rows), default=0),
            "ledger_digest": hashlib.sha256(canonical(rows).encode()).hexdigest(),
            "ledger_count": len(rows),
        }
        temporary = directory / "manifest.partial"
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(canonical(manifest) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, directory / "manifest.json")
        fsync(target)
        fsync(directory)
        fsync(parent)
        backup_info(directory)
        prune_backups(path, now_ms)
        return directory, manifest
    except BaseException:
        # An incomplete backup is never accepted or used as permission to delete.
        shutil.rmtree(directory)
        raise


def purge(db, ids):
    if not ids:
        return
    encoded = canonical(ids)
    membership = " IN (SELECT value FROM json_each(?))"
    rows = db.execute(
        "SELECT * FROM tracking_outbox WHERE json_extract(envelope,'$.payload.tweet_id')" + membership,
        (encoded,),
    ).fetchall()
    for row in rows:
        envelope = json.loads(row["envelope"])
        minimal = {
            k: envelope[k]
            for k in (
                "schema_version",
                "event_id",
                "source",
                "event_type",
                "tenant_id",
                "project_id",
                "correlation_id",
                "received_at",
            )
            if k in envelope
        }
        minimal["expired"] = True
        receipt = None
        if row["receipt"]:
            try:
                raw = json.loads(row["receipt"])
                if isinstance(raw, dict):
                    receipt = canonical(
                        {
                            key: raw[key]
                            for key in (
                                "event_id",
                                "project_id",
                                "receipt_id",
                                "accepted_at",
                                "duplicate",
                                "request_id",
                            )
                            if key in raw
                        }
                    )
            except (ValueError, TypeError):
                pass
        db.execute(
            "UPDATE tracking_outbox SET envelope=?,original_hash=COALESCE(original_hash,?),receipt=?,original_receipt_hash=COALESCE(original_receipt_hash,?),state=?,updated_at=? WHERE event_id=?",
            (
                canonical(minimal),
                hashlib.sha256(row["envelope"].encode()).hexdigest(),
                receipt,
                hashlib.sha256(row["receipt"].encode()).hexdigest() if row["receipt"] else None,
                "expired_pending_reconciliation" if row["state"] == "pending" else row["state"],
                time.time(),
                row["event_id"],
            ),
        )
    db.execute("DELETE FROM receipts WHERE key IN (SELECT 'tracking.quote.v1:' || value FROM json_each(?))", (encoded,))
    db.execute("DELETE FROM tweets WHERE tweet_id" + membership, (encoded,))
    db.execute("DELETE FROM tweets_legacy WHERE tweet_id" + membership, (encoded,))
    db.execute("DELETE FROM changes WHERE json_extract(data,'$.tweet_id')" + membership, (encoded,))
    db.execute(
        "UPDATE tweet_ledger SET state='expired',first_received_at_ms=NULL,origin_subscription_id=NULL WHERE tweet_id"
        + membership,
        (encoded,),
    )
    db.execute("DELETE FROM feed_bases")
    db.execute("DELETE FROM feed_snapshots")
    db.execute("UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1")


def cleanup(store, *, now_ms=None, owner=None, backup=backup_database, fault=None):
    now_ms = wall_ms() if now_ms is None else now_ms
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = retention_now(db, now_ms)
        meta = db.execute("SELECT * FROM feed_meta WHERE singleton=1").fetchone()
        db.execute("DELETE FROM feed_bases WHERE expires_at_ms<=?", (now,))
        db.execute("DELETE FROM feed_snapshots WHERE expires_at_ms<=?", (now,))
        if meta["clock_anomaly"]:
            db.execute("COMMIT")
            return {"state": "clock_anomaly", "deleted": 0}
        if owner:
            lease = db.execute("SELECT worker_id,heartbeat FROM runtime WHERE id=1").fetchone()
            if lease["worker_id"] != owner or lease["heartbeat"] < time.time() - 30:
                raise ValueError("retention lease lost")
        pending = db.execute(
            "SELECT 1 FROM tweet_ledger WHERE expires_at_ms<=? AND (state!='expired' OR EXISTS(SELECT 1 FROM tweets WHERE tweets.tweet_id=tweet_ledger.tweet_id)) LIMIT 1",
            (now,),
        ).fetchone()
        old = db.execute(
            "SELECT * FROM retention_jobs WHERE state IN ('backing_up','verified','deleting','blocked_backup') ORDER BY created_at_ms DESC LIMIT 1"
        ).fetchone()
        if not pending:
            db.execute("COMMIT")
            prune_backups(store.path, now)
            return {"state": "completed", "deleted": 0}
        if old and old["retry_at_ms"] > now:
            db.execute("COMMIT")
            return {"state": "blocked_backup", "deleted": 0}
        job = old["job_id"] if old else "ret_" + str(uuid.uuid4())
        db.execute(
            "INSERT OR IGNORE INTO retention_jobs(job_id,state,created_at_ms,updated_at_ms) VALUES(?,'scheduled',?,?)",
            (job, now, now),
        )
        db.execute("UPDATE retention_jobs SET state='backing_up',updated_at_ms=? WHERE job_id=?", (now, job))
        db.execute("COMMIT")
    try:
        if old and old["backup_path"]:
            directory = Path(old["backup_path"])
            manifest = backup_info(directory)
            if manifest["sha256"] != old["backup_sha256"]:
                raise ValueError("retention backup changed")
        else:
            directory, manifest = backup(store.path, job_id=job + "_" + str(uuid.uuid4()), now_ms=now)
        with store.connect() as db:
            db.execute(
                "UPDATE retention_jobs SET state='verified',backup_path=?,backup_sha256=?,high_water=?,updated_at_ms=? WHERE job_id=?",
                (str(directory), manifest["sha256"], manifest["ledger_high_water"], now, job),
            )
        if fault == "after_backup":
            raise RuntimeError("injected interruption")
        deleted = 0
        while True:
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if owner:
                    lease = db.execute("SELECT worker_id,heartbeat FROM runtime WHERE id=1").fetchone()
                    if lease["worker_id"] != owner or lease["heartbeat"] < time.time() - 30:
                        raise ValueError("retention lease lost")
                if db.execute("SELECT clock_anomaly FROM feed_meta WHERE singleton=1").fetchone()[0]:
                    db.execute("ROLLBACK")
                    return {"state": "clock_anomaly", "deleted": deleted}
                ids = [
                    r[0]
                    for r in db.execute(
                        "SELECT tweet_id FROM tweet_ledger WHERE first_seq<=? AND expires_at_ms<=? AND (state!='expired' OR EXISTS(SELECT 1 FROM tweets WHERE tweets.tweet_id=tweet_ledger.tweet_id)) ORDER BY first_seq LIMIT 1000",
                        (manifest["ledger_high_water"], now),
                    )
                ]
                if not ids:
                    db.execute(
                        "UPDATE retention_jobs SET state='completed',error=NULL,updated_at_ms=? WHERE job_id=?",
                        (now, job),
                    )
                    db.execute("COMMIT")
                    break
                db.execute("UPDATE retention_jobs SET state='deleting' WHERE job_id=?", (job,))
                purge(db, ids)
                db.execute(
                    "UPDATE retention_jobs SET deleted_count=deleted_count+?,updated_at_ms=? WHERE job_id=?",
                    (len(ids), now, job),
                )
                if fault == "in_delete":
                    raise RuntimeError("injected delete failure")
                db.execute("COMMIT")
                deleted += len(ids)
        return {"state": "completed", "deleted": deleted, "job_id": job}
    except (OSError, ValueError, sqlite3.Error, RuntimeError):
        with store.connect() as db:
            attempts = (
                db.execute("SELECT attempts FROM retention_jobs WHERE job_id=?", (job,)).fetchone()[0] + 1
            )
            db.execute(
                "UPDATE retention_jobs SET state='blocked_backup',error='backup_or_delete_failed',attempts=?,retry_at_ms=?,updated_at_ms=? WHERE job_id=?",
                (attempts, now + min(1800000, 60000 * 2 ** min(attempts - 1, 5)), now, job),
            )
        return {"state": "blocked_backup", "deleted": 0, "job_id": job}


def control_hash(db):
    tables = ("projects", "commands", "public_receipts", "receipts", "audit")
    return hashlib.sha256(
        canonical(
            {
                table: [list(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
                for table in tables
            }
        ).encode()
    ).hexdigest()


def restore(directory, destination, ledger_source, *, expected_watermark, fault=None):
    """Offline, new-path recovery. No commit admits an incomplete target to runtime."""
    from .migration import inspect, safe_path
    from .store import Store

    def boundary(name):
        if fault == name:
            raise RuntimeError("injected restore interruption: " + name)

    directory = guard_path(directory)
    manifest = backup_info(directory)
    if manifest["schema_version"] != 4:
        raise ValueError("restore requires v4 verified backup")
    destination = safe_path(destination)
    if destination.exists() or expected_watermark < manifest["ledger_high_water"]:
        raise ValueError("restore requires new path and nonregressing watermark")
    candidate = guard_path(ledger_source)
    if candidate.is_dir():
        if candidate == directory:
            raise ValueError("recovery bundle cannot be its own ledger authority")
        source_manifest = backup_info(candidate)
        if (
            source_manifest["schema_version"] != 4
            or source_manifest["created_at_ms"] < manifest["created_at_ms"]
        ):
            raise ValueError("independent ledger backup is older than recovery bundle")
        source = candidate / "tracking.db"
    else:
        source = safe_path(candidate)
        if source.is_relative_to(directory.parent) or source == destination:
            raise ValueError("independent current ledger authority required")
        inspect(source)
    if source.samefile(directory / "tracking.db"):
        raise ValueError("recovery bundle cannot be its own ledger authority")
    with connection(source.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if db.execute("SELECT clock_anomaly FROM feed_meta WHERE singleton=1").fetchone()[0]:
            raise ValueError("acknowledge source clock before restore")
        lease = db.execute("SELECT heartbeat FROM runtime WHERE id=1").fetchone()
        if not candidate.is_dir() and lease and lease[0] and lease[0] > time.time() - 30:
            raise ValueError("stop the source worker before restoring its ledger")
        controls = control_hash(db)
        horizon = [dict(r) for r in db.execute("SELECT * FROM tweet_ledger ORDER BY first_seq")]
        retained_now = db.execute("SELECT last_retention_now_ms FROM feed_meta WHERE singleton=1").fetchone()[
            0
        ]
        db.execute("COMMIT")
    if max((r["first_seq"] for r in horizon), default=0) < expected_watermark:
        raise ValueError("ledger horizon cannot be proven")
    by_id = {r["tweet_id"]: r for r in horizon}
    with connection((directory / "tracking.db").as_uri() + "?mode=ro", uri=True) as db:
        if control_hash(db) != controls:
            raise ValueError("recovery bundle has stale control state; create a fresh verified backup")
        meta = db.execute("SELECT database_path,clock_anomaly FROM feed_meta WHERE singleton=1").fetchone()
        if str(destination) == meta[0]:
            raise ValueError("restore requires a genuinely new path")
        if meta[1]:
            raise ValueError("clock-anomalous backup requires separate review")
        for tweet_id, expiry in db.execute("SELECT tweet_id,expires_at_ms FROM tweet_ledger"):
            if tweet_id not in by_id or by_id[tweet_id]["expires_at_ms"] > expiry:
                raise ValueError("ledger source regresses known tweet history")
    safe_path(destination, create=True)
    with (
        connection((directory / "tracking.db").as_uri() + "?mode=ro", uri=True) as src,
        connection(destination, isolation_level=None) as dst,
    ):
        src.backup(dst)
        boundary("after_copy")
        # Until this transaction commits, the copied physical path rejects startup.
        # Its first identifying write makes the target INACTIVE in the same commit.
        dst.execute("BEGIN IMMEDIATE")
        dst.execute(
            "UPDATE feed_meta SET database_path=?,recovery_ready=0,snapshot_epoch=?,semantic_revision=semantic_revision+1,last_retention_now_ms=MAX(last_retention_now_ms,?) WHERE singleton=1",
            (str(destination), str(uuid.uuid4()), retained_now),
        )
        dst.execute("DELETE FROM feed_bases")
        dst.execute("DELETE FROM feed_snapshots")
        dst.execute("DELETE FROM changes")
        dst.execute("UPDATE runtime SET worker_id=NULL,heartbeat=0,connection='disconnected',pong_at=NULL")
        dst.execute("COMMIT")
    boundary("after_inactivate")
    store = Store(destination, _restoring=True)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM tweet_ledger")
        for row in horizon:
            keys = list(row)
            db.execute(
                "INSERT INTO tweet_ledger("
                + ",".join(keys)
                + ") VALUES("
                + ",".join("?" for _ in keys)
                + ")",
                tuple(row.values()),
            )
        db.execute("COMMIT")
    boundary("after_ledger")
    result = cleanup(store)
    if result["state"] != "completed":
        raise ValueError("restore retention verification blocked")
    boundary("after_cleanup")
    # Validation precedes the only activation commit; a failed check leaves ready=0.
    inspect(destination, allow_recovery=True)
    with store.connect() as db:
        if (
            db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("restored integrity invalid")
        actual = {r["tweet_id"]: dict(r) for r in db.execute("SELECT * FROM tweet_ledger")}
        if set(actual) != set(by_id) or any(
            actual[key]["expires_at_ms"] > row["expires_at_ms"] for key, row in by_id.items()
        ):
            raise ValueError("restored ledger validation failed")
    fsync(destination)
    boundary("before_activate")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE feed_meta SET recovery_ready=1 WHERE singleton=1")
        db.execute("COMMIT")
    fsync(destination)
    boundary("after_activate")
    inspect(destination)
    return {
        "restored": True,
        "ledger_high_water": max((r["first_seq"] for r in horizon), default=0),
        "expired_deleted": result["deleted"],
    }
