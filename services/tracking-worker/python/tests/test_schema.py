import sqlite3

import pytest

from tracking.store import APP_ID, Store


def test_upgrade_existing_foundation_and_checksum_guard(tmp_path):
    path = tmp_path / "tracking.db"
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA application_id={APP_ID}")
        db.executescript("""CREATE TABLE _schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL);
            CREATE TABLE _store_identity(singleton INTEGER PRIMARY KEY,store_name TEXT NOT NULL);
            INSERT INTO _schema_migrations VALUES(1,'foundation','2026-10-15');
            INSERT INTO _store_identity VALUES(1,'tracking');""")
    store = Store(path)
    with store.connect() as db:
        rows = db.execute("SELECT version,name,checksum FROM _schema_migrations ORDER BY version").fetchall()
        assert [(r[0], r[1]) for r in rows] == [(1, "foundation"), (2, "tracking_new_tweet_v1")]
        assert len(rows[1][2]) == 64
        db.execute("UPDATE _schema_migrations SET checksum='tampered' WHERE version=2")
    with pytest.raises(ValueError, match="checksum"):
        Store(path)


def test_identity_mismatch_is_rejected(tmp_path):
    path = tmp_path / "tracking.db"
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA application_id={APP_ID}")
        db.executescript(
            "CREATE TABLE _store_identity(singleton INTEGER PRIMARY KEY,store_name TEXT); INSERT INTO _store_identity VALUES(1,'hunter');"
        )
    with pytest.raises(ValueError, match="owner mismatch"):
        Store(path)
