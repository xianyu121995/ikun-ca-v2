import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_ops.py"
spec = importlib.util.spec_from_file_location("release_ops", SCRIPT)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class ReleaseOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "ikun-ca-v2-deployment"
        self.envroot = self.root / "staging"
        self.release = self.root / "releases" / "candidate"
        self.cfgpath = self.envroot / "config" / "release.local.json"
        self.raw = {"environment": "staging", "deployment_root": str(self.root),
                    "release_path": str(self.release), "release_commit": "a" * 40,
                    "databases": {k: str(self.envroot / "data" / k / v) for k, v in ops.DATABASES.items()},
                    "services": {name: {"port": 3310 + i, "host": "127.0.0.1", "argv": [sys.executable, "service.py"],
                                        "environment_file": str(self.envroot / "config" / (name + ".secret.json")),
                                        "environment": {"IKUN_REMOTE_ENABLED": "false"}}
                                 for i, name in enumerate(ops.SERVICES)}}
        self.save()

    def save(self):
        self.cfgpath.parent.mkdir(parents=True, exist_ok=True)
        self.cfgpath.write_text(json.dumps(self.raw))
        return ops.config(self.cfgpath)

    def databases(self):
        self.connections = []
        for path in self.raw["databases"].values():
            db = Path(path)
            db.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(db)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
            con.execute("INSERT INTO items VALUES(1,'persistent event')")
            con.commit()
            self.connections.append(con)
            self.addCleanup(con.close)
        return self.save()

    def test_four_physically_separate_databases(self):
        cfg = self.databases()
        self.assertEqual(len({Path(p).stat().st_ino for p in cfg["databases"].values()}), 4)

    def test_deleting_each_domain_does_not_change_other_domains(self):
        self.databases()
        for index, con in enumerate(self.connections):
            con.execute("DELETE FROM items")
            con.commit()
            for other in self.connections[index + 1:]:
                self.assertEqual(other.execute("SELECT count(*) FROM items").fetchone()[0], 1)

    def test_reject_same_database_path(self):
        self.raw["databases"]["tracking"] = self.raw["databases"]["hunter"]
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_shared_symlink(self):
        self.databases()
        db = Path(self.raw["databases"]["tracking"])
        db.unlink()
        db.symlink_to(self.raw["databases"]["hunter"])
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_shared_hardlink(self):
        self.databases()
        db = Path(self.raw["databases"]["tracking"])
        db.unlink()
        os.link(self.raw["databases"]["hunter"], db)
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_database_parent_symlink(self):
        directory = self.envroot / "data"
        directory.parent.mkdir(parents=True, exist_ok=True)
        other = self.root / "external"
        other.mkdir(parents=True)
        directory.symlink_to(other)
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_cross_environment_path(self):
        self.raw["databases"]["hunter"] = str(self.root / "production" / "data" / "hunter" / "hunter.db")
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_development_server(self):
        self.raw["services"]["web"]["argv"] = ["/bin/node", "next", "dev"]
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_public_bind(self):
        self.raw["services"]["hunter"]["host"] = "0.0.0.0"
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_reject_duplicate_port(self):
        self.raw["services"]["tracking"]["port"] = self.raw["services"]["hunter"]["port"]
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_wal_backup_restore_preserves_committed_event(self):
        cfg = self.databases()
        dest = ops.backup(cfg)
        restored = ops.restore_to_empty(cfg, dest, self.envroot / "restore-drills" / "first")
        for name in ops.DATABASES:
            con = sqlite3.connect(restored / name / ops.DATABASES[name])
            try:
                self.assertEqual(con.execute("SELECT name FROM items").fetchone()[0], "persistent event")
            finally:
                con.close()
        self.assertFalse(ops.read_json(dest / "manifest.json")["cross_database_atomic"])

    def test_backup_permissions(self):
        dest = ops.backup(self.databases())
        self.assertEqual(dest.stat().st_mode & 0o777, 0o700)
        for path in dest.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_restore_never_overwrites_existing_destination(self):
        cfg = self.databases()
        dest = ops.backup(cfg)
        with self.assertRaises(ops.Blocked):
            ops.restore_to_empty(cfg, dest, self.envroot / "data")
        target = self.envroot / "restore-drills" / "exists"
        target.mkdir(parents=True)
        with self.assertRaises(ops.Blocked):
            ops.restore_to_empty(cfg, dest, target)

    def test_corrupted_backup_rejected_before_destination_creation(self):
        cfg = self.databases()
        dest = ops.backup(cfg)
        (dest / "hunter.db").write_bytes(b"corrupt")
        target = self.envroot / "restore-drills" / "corrupt"
        with self.assertRaises(ops.Blocked):
            ops.restore_to_empty(cfg, dest, target)
        self.assertFalse(target.exists())

    def test_missing_database_does_not_create_fake_backup(self):
        with self.assertRaises(ops.Blocked):
            ops.backup(self.save())
        self.assertFalse((self.envroot / "backups").exists())

    def test_launchd_renders_exactly_three_independent_services(self):
        out = ops.render(self.save(), self.cfgpath, self.envroot / "plans" / "first")
        plists = list(out.glob("*.plist"))
        self.assertEqual(len(plists), 3)
        for path in plists:
            record = plistlib.loads(path.read_bytes())
            self.assertTrue(record["KeepAlive"])
            self.assertEqual(record["ThrottleInterval"], 30)
            self.assertEqual(record["ExitTimeOut"], 30)
            self.assertEqual(record["Umask"], 0o077)
        self.assertFalse(ops.read_json(out / "plan.json")["installed"])

    def test_render_refuses_overwrite(self):
        cfg = self.save()
        dest = self.envroot / "plans" / "first"
        ops.render(cfg, self.cfgpath, dest)
        with self.assertRaises(ops.Blocked):
            ops.render(cfg, self.cfgpath, dest)

    def test_launchdaemon_has_nonroot_owner(self):
        out = ops.render(self.save(), self.cfgpath, self.envroot / "plans" / "first", "lvlei")
        for path in out.glob("*.plist"):
            self.assertEqual(plistlib.loads(path.read_bytes())["UserName"], "lvlei")

    def production(self):
        prod = copy.deepcopy(self.raw)
        prod["environment"] = "production"
        prod["databases"] = {k: v.replace("/staging/", "/production/") for k, v in prod["databases"].items()}
        for value in prod["services"].values():
            value["environment_file"] = value["environment_file"].replace("/staging/", "/production/")
        self.raw = prod
        return self.save()

    def test_production_requires_explicit_bound_approval(self):
        cfg = self.production()
        with self.assertRaises(ops.Blocked):
            ops.publish_approval(cfg, self.cfgpath, None)
        record = self.root / "wrong.approval.json"
        ops.write_new(record, {"operation": "publish_production", "release_commit": "b" * 40,
                               "config_sha256": ops.digest(self.cfgpath), "approved_by": "user"})
        with self.assertRaises(ops.Blocked):
            ops.publish_approval(cfg, self.cfgpath, record)

    def test_production_plan_does_not_grant_approval(self):
        cfg = self.production()
        out = ops.render(cfg, self.cfgpath, self.root / "production" / "plans" / "first")
        self.assertFalse(ops.read_json(out / "plan.json")["started"])
        for path in out.glob("*.plist"):
            self.assertIn("--approval", plistlib.loads(path.read_bytes())["ProgramArguments"])

    def test_secret_permissions_and_public_exposure_rejected(self):
        cfg = self.save()
        secret = Path(cfg["services"]["web"]["environment_file"])
        ops.write_new(secret, {"NEXT_PUBLIC_API_KEY": "test-secret"})
        with self.assertRaises(ops.Blocked):
            ops.service_environment(cfg, "web")
        secret.write_text("{}")
        secret.chmod(0o644)
        with self.assertRaises(ops.Blocked):
            ops.service_environment(cfg, "web")

    def test_remote_enabled_in_staging_rejected(self):
        self.raw["services"]["hunter"]["environment"]["IKUN_REMOTE_ENABLED"] = "true"
        cfg = self.save()
        ops.write_new(cfg["services"]["hunter"]["environment_file"], {})
        with self.assertRaises(ops.Blocked):
            ops.service_environment(cfg, "hunter")

    def test_child_does_not_inherit_arbitrary_secrets(self):
        cfg = self.save()
        ops.write_new(cfg["services"]["web"]["environment_file"], {})
        os.environ["LEGACY_SHARED_API_KEY"] = "legacy-secret"
        self.addCleanup(os.environ.pop, "LEGACY_SHARED_API_KEY", None)
        env = ops.service_environment(cfg, "web")
        self.assertNotIn("LEGACY_SHARED_API_KEY", env)
        self.assertEqual(env["NODE_ENV"], "production")

    def test_secret_not_echoed_in_cli_error(self):
        self.raw["environment"] = "test-secret-do-not-print"
        self.cfgpath.write_text(json.dumps(self.raw))
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", "--config", str(self.cfgpath)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("test-secret", result.stdout + result.stderr)

    def test_launchd_output_cannot_touch_legacy_directory(self):
        with self.assertRaises(ops.Blocked):
            ops.render(self.save(), self.cfgpath, self.root / "legacy")
        self.assertFalse((self.root / "legacy").exists())

    def test_launchdaemon_cannot_run_as_root(self):
        with self.assertRaises(ops.Blocked):
            ops.render(self.save(), self.cfgpath, self.envroot / "plans" / "root", "root")


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Release Tool Test")
        self.git("config", "user.email", "test@localhost")
        report = self.root / "fixture-acceptance.json"
        report.write_text('{"fixture_only":true,"status":"PASS"}')
        self.manifest = {"repository": str(self.repo), "base_ref": "main", "modules": [
            {"name": name, "ref": None, "commit": None, "acceptance": "PENDING", "report_path": str(report),
             "report_sha256": ops.digest(report)} for name in ("foundation", "ui", "auth", "hunter", "tracking", "homepage")]}
        self.manifest_path = self.root / "modules.json"

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        return result.stdout.strip()

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest))
        return ops.intake(self.manifest_path)

    def accept_fixture(self):
        (self.repo / "fixture.txt").write_text("fixture\n")
        self.git("add", "fixture.txt")
        self.git("commit", "-m", "test-only foundation")
        head = self.git("rev-parse", "HEAD")
        for entry in self.manifest["modules"]:
            entry.update({"ref": "main", "commit": head, "acceptance": "ACCEPTED"})
        return self.save()

    def test_unborn_repo_and_pending_modules_blocked(self):
        result = self.save()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["base_commit"])
        self.assertEqual(len(result["modules"]), 6)
        self.assertTrue(all(x["blockers"] for x in result["modules"]))

    def test_missing_module_is_not_silently_skipped(self):
        self.manifest["modules"].pop()
        with self.assertRaises(ops.Blocked):
            self.save()

    def test_moved_reference_blocks_merge(self):
        self.accept_fixture()
        self.manifest["modules"][0]["commit"] = "b" * 40
        self.assertEqual(self.save()["status"], "BLOCKED")

    def test_changed_acceptance_report_blocks_merge(self):
        self.accept_fixture()
        Path(self.manifest["modules"][0]["report_path"]).write_text("changed")
        self.assertEqual(self.save()["status"], "BLOCKED")

    def test_isolated_merge_does_not_change_source_repository(self):
        result = self.accept_fixture()
        self.assertEqual(result["status"], "READY_FOR_ISOLATED_MERGE")
        before = self.git("rev-parse", "HEAD")
        clone = self.root / "isolated-merge" / "candidate"
        merged = ops.assemble(self.manifest_path, clone)
        self.assertEqual(merged["status"], "MERGED_PENDING_INTEGRATION_TESTS")
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(ops.git(clone, "branch", "--show-current"), "codex/ikun-ca-v2-final-integration")

    def test_pending_manifest_never_creates_merge_checkout(self):
        self.save()
        clone = self.root / "isolated-merge" / "candidate"
        with self.assertRaises(ops.Blocked):
            ops.assemble(self.manifest_path, clone)
        self.assertFalse(clone.exists())


if __name__ == "__main__":
    unittest.main()
