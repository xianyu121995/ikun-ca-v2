import hashlib
import sqlite3
from pathlib import Path

import pytest

from tracking.migration import APP_ID, SCHEMAS, inspect, migrate
from tracking.store import Store


@pytest.fixture(autouse=True)
def tracking_directory(tmp_path):
    (tmp_path / "tracking").mkdir()


def test_no_runtime_ddl_or_creation(tmp_path):
    path = tmp_path / "tracking" / "tracking.db"
    with pytest.raises((ValueError, sqlite3.Error, OSError)):
        Store(path)
    assert not path.exists()
    migrate(path)
    before = path.read_bytes()
    Store(path)
    inspect(path)
    assert before == path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600 and path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("columns", [3, 4])
def test_foundation_upgrade_preserves_metadata(tmp_path, columns):
    path = tmp_path / "tracking" / "tracking.db"
    with sqlite3.connect(path) as db:
        db.executescript((SCHEMAS / "001_foundation.sql").read_text())
        if columns == 4:
            db.execute("ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT")
        db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'tracking')")
        db.execute("INSERT INTO _schema_migrations(version,name,applied_at) VALUES(1,'foundation','old')")
        db.execute(f"PRAGMA application_id={APP_ID}")
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT applied_at FROM _schema_migrations WHERE version=1").fetchone()[0] == "old"
        assert db.execute("SELECT COUNT(*) FROM _migration_checksums").fetchone()[0] == 4
    inspect(path)


def legacy(path, human=False):
    sql = (SCHEMAS / "002_legacy_reference.sql").read_text()
    with sqlite3.connect(path) as db:
        db.executescript(sql)
        db.execute(f"PRAGMA application_id={APP_ID}")
        db.execute("ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT")
        db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'tracking')")
        db.execute(
            "INSERT INTO _schema_migrations(version,name,applied_at,checksum) VALUES(2,?,?,?)",
            ("tracking_new_tweet_v1", "old", hashlib.sha256(sql.encode()).hexdigest()),
        )
        db.execute(
            "INSERT INTO projects(project_id,name,handle,confirmed_by,confirmed_at,desired,generation_at,created_at,updated_at) VALUES('prj_550e8400-e29b-41d4-a716-446655440001','p','project1','old-actor',1,'running',1,1,1)"
        )
        db.execute(
            "INSERT INTO tweets(project_id,handle,tweet_id,text,created_at,received_at,source,generation) VALUES('prj_550e8400-e29b-41d4-a716-446655440001','project1','123','old text',2,2,'wss',1)"
        )
        db.execute("INSERT INTO receipts(key,fingerprint,result,at) VALUES('old-key','hash','{}',1)")
        if human:
            db.execute(
                "INSERT INTO sessions(digest,role,expires) VALUES('old-live-session','superadmin',9999999999)"
            )


def test_actual_candidate_upgrade_restart_backup_new_path(tmp_path):
    path = tmp_path / "tracking" / "tracking.db"
    legacy(path)
    migrate(path)
    first = Store(path)
    sid = first.projects()[0]["subscription_id"]
    assert sid.startswith("sub_") and first.activities() == []
    with first.connect() as db:
        assert db.execute("SELECT text FROM tweets").fetchone()[0] == "old text"
    assert Store(path).projects()[0]["subscription_id"] == sid
    target = tmp_path / "restored/tracking/tracking.db"
    target.parent.mkdir(parents=True)
    with sqlite3.connect(path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with pytest.raises(ValueError, match="explicit verified restore"):
        Store(target)
    from tracking.retention import backup_database, restore

    directory, manifest = backup_database(path)
    checked = tmp_path / "verified/tracking/tracking.db"
    restore(directory, checked, path, expected_watermark=manifest["ledger_high_water"])
    assert Store(checked).projects()[0]["subscription_id"] == sid
    with first.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


def test_live_legacy_identity_blocks_upgrade_without_deleting(tmp_path):
    path = tmp_path / "tracking" / "tracking.db"
    legacy(path, True)
    with pytest.raises(ValueError, match="identity retirement"):
        migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='commands'").fetchall()


def test_migration_failure_transaction_rolls_back(tmp_path):
    path = tmp_path / "tracking" / "tracking.db"
    legacy(path)
    with pytest.raises(RuntimeError):
        migrate(path, fault=3)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT text FROM tweets").fetchone()[0] == "old text"
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='commands'").fetchall()
    migrate(path)
    inspect(path)


@pytest.mark.parametrize(
    "mode", ["checksum", "future", "alias", "foreign", "owner", "table", "index", "ledger", "version"]
)
def test_unsafe_or_mismatched_schema_rejected(tmp_path, mode):
    path = tmp_path / "tracking" / "tracking.db"
    migrate(path)
    if mode == "alias":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError):
            Store(alias / "tracking.db")
        return
    with sqlite3.connect(path) as db:
        if mode == "checksum":
            db.execute("UPDATE _migration_checksums SET sha256='wrong' WHERE version=3")
        elif mode == "future":
            db.execute("PRAGMA user_version=999")
        elif mode == "table":
            db.execute("DROP TABLE commands")
        elif mode == "index":
            db.execute("DROP INDEX subscriptions_identity")
        elif mode == "ledger":
            db.execute("UPDATE _schema_migrations SET name='foreign_migration' WHERE version=3")
        elif mode == "version":
            db.execute("PRAGMA user_version=2")
        elif mode == "owner":
            db.execute("UPDATE _store_identity SET store_name='hunter'")
        else:
            db.execute("PRAGMA application_id=123")
    with pytest.raises(ValueError):
        Store(path)
    with pytest.raises(ValueError):
        migrate(path)


def test_legacy_invalid_project_mapping_is_preserved_for_review(tmp_path):
    path = tmp_path / "tracking" / "tracking.db"
    legacy(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE projects SET project_id='old-unmapped-id'")
    with pytest.raises(ValueError, match="mapping requires explicit review"):
        migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT project_id FROM projects").fetchone()[0] == "old-unmapped-id"
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='commands'").fetchall()


@pytest.mark.parametrize("mode", ["symlink", "hardlink", "wal_symlink", "wal_hardlink"])
def test_database_and_sidecar_aliases_preserve_protected_target(tmp_path, mode):
    path = tmp_path / "tracking" / "tracking.db"
    migrate(path)
    protected = tmp_path / "protected-fixture"
    protected.write_bytes(b"protected fixture must not change")
    alias = Path(str(path) + ("-wal" if mode.startswith("wal_") else ""))
    alias.unlink(missing_ok=True)
    if mode.endswith("symlink"):
        alias.symlink_to(protected)
    else:
        alias.hardlink_to(protected)
    with pytest.raises(ValueError):
        Store(path)
    with pytest.raises(ValueError):
        migrate(path)
    assert protected.read_bytes() == b"protected fixture must not change"


@pytest.mark.parametrize("mode", ["removed", "foreign", "sidecar"])
def test_runtime_database_changes_are_rejected_without_creation_or_write(tmp_path, mode):
    path = tmp_path / "tracking" / "tracking.db"
    migrate(path)
    store = Store(path)
    if mode == "sidecar":
        protected = tmp_path / "protected-fixture"
        protected.write_bytes(b"protected sidecar")
        alias = Path(str(path) + "-wal")
        alias.unlink(missing_ok=True)
        alias.symlink_to(protected)
        before = protected.read_bytes()
    else:
        path.unlink()
        if mode == "foreign":
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE protected_fixture(value TEXT)")
                db.execute(f"PRAGMA application_id={APP_ID}")
                db.execute("CREATE TABLE _store_identity(singleton INTEGER,store_name TEXT)")
                db.execute("INSERT INTO _store_identity VALUES(1,'hunter')")
            before = path.read_bytes()
    with pytest.raises((ValueError, sqlite3.Error)):
        store.projects()
    if mode == "removed":
        assert not path.exists()
    else:
        assert (protected if mode == "sidecar" else path).read_bytes() == before


def test_sidecar_disappearance_uses_one_lstat_and_preserves_runtime_boundary(tmp_path, monkeypatch):
    path = tmp_path / "tracking/tracking.db"
    migrate(path)
    original = Path.lstat
    calls = {}

    def disappearing(candidate, *args, **kwargs):
        if str(candidate).endswith(("-wal", "-shm")):
            calls[str(candidate)] = calls.get(str(candidate), 0) + 1
            raise FileNotFoundError(str(candidate))
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", disappearing)
    from tracking.migration import safe_path

    assert safe_path(path) == path
    assert set(calls.values()) == {1}
    with Store(path).connect() as db:
        assert db.execute("SELECT store_name FROM _store_identity").fetchone()[0] == "tracking"


def test_non_regular_sidecar_is_rejected_without_opening_it(tmp_path):
    import os

    path = tmp_path / "tracking/tracking.db"
    migrate(path)
    fifo = Path(str(path) + "-wal")
    fifo.unlink(missing_ok=True)  # Private, stopped fixture only; arrange an invalid sidecar.
    os.mkfifo(fifo, 0o600)
    with pytest.raises(ValueError, match="alias rejected"):
        Store(path)
