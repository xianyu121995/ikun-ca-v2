#!/usr/bin/env python3
"""Local release tooling. No DNS/Watch mutation and no implicit production apply."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

SERVICES = ("web", "hunter", "tracking")
DATABASES = {"hunter": "hunter.db", "tracking": "tracking.db", "projects": "projects.db", "auth": "auth.db"}


class Blocked(ValueError):
    pass


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def private_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def write_new(path, data):
    path = Path(path)
    private_dir(path.parent)
    raw = data if isinstance(data, bytes) else (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def copy_new(source, target):
    target = Path(target)
    private_dir(target.parent)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output, Path(source).open("rb") as stream:
        shutil.copyfileobj(stream, output, length=1024 * 1024)
        output.flush()
        os.fsync(output.fileno())


def contained(path, parent):
    path, parent = Path(path).absolute(), Path(parent).absolute()
    if path == parent or parent not in path.parents:
        raise Blocked("path must be beneath its isolated root")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Blocked("symlink in isolated path")
    return path


def config(path):
    cfg = read_json(path)
    if cfg.get("environment") not in ("staging", "production"):
        raise Blocked("environment must be staging or production")
    env = cfg["environment"]
    root = Path(cfg["deployment_root"])
    if not root.is_absolute() or root.name != "ikun-ca-v2-deployment":
        raise Blocked("use an absolute dedicated ikun-ca-v2-deployment root")
    envroot = contained(root / env, root)
    cfg["envroot"] = str(envroot)
    release = contained(Path(cfg["release_path"]), root / "releases")
    cfg["release_path"] = str(release)
    if not re.fullmatch(r"[0-9a-f]{40}", cfg.get("release_commit", "")):
        raise Blocked("release_commit must be a pinned Git SHA")
    if set(cfg.get("databases", {})) != set(DATABASES):
        raise Blocked("three business databases plus independent auth are required")
    seen_paths, seen_files = set(), set()
    for name, filename in DATABASES.items():
        db = contained(Path(cfg["databases"][name]), envroot / "data")
        if db.name != filename or db.parent.name != name:
            raise Blocked("database filename and dedicated domain directory mismatch")
        if str(db) in seen_paths:
            raise Blocked("database paths overlap")
        seen_paths.add(str(db))
        if db.exists():
            stat = db.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity in seen_files or stat.st_nlink != 1:
                raise Blocked("hardlinked database is forbidden")
            seen_files.add(identity)
    if set(cfg.get("services", {})) != set(SERVICES):
        raise Blocked("exactly three independent primary services are required")
    ports = set()
    for name in SERVICES:
        spec = cfg["services"][name]
        port = spec.get("port")
        if not isinstance(port, int) or port in ports or not 1024 < port < 65536:
            raise Blocked("ports must be unique nonprivileged integers")
        ports.add(port)
        if spec.get("host") != "127.0.0.1":
            raise Blocked("all origins must bind loopback")
        argv = spec.get("argv", [])
        if not argv or any(not isinstance(arg, str) or not arg for arg in argv):
            raise Blocked("argv must be a nonempty string array")
        if any(arg in ("dev", "--reload", "--watch") for arg in argv):
            raise Blocked("development servers/watchers cannot be deployed")
        secret = contained(Path(spec["environment_file"]), envroot / "config")
        spec["environment_file"] = str(secret)
        if not isinstance(spec.get("environment", {}), dict):
            raise Blocked("service environment must be a mapping")
    other = "production" if env == "staging" else "staging"
    if any(str(root / other) in item for item in seen_paths):
        raise Blocked("environment database paths overlap")
    return cfg


def check_database(path):
    db = Path(path)
    if not db.is_file():
        raise Blocked("database does not exist")
    connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise Blocked("SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise Blocked("SQLite foreign key check failed")
    finally:
        connection.close()


def backup(cfg, timeout=30):
    # A consistent snapshot per DB, not a cross-database distributed transaction.
    for path in cfg["databases"].values():
        check_database(path)
    parent = contained(Path(cfg["envroot"]) / "backups", Path(cfg["envroot"]))
    dest = parent / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    private_dir(dest)
    manifest = {"created_at": utcnow(), "environment": cfg["environment"],
                "release_commit": cfg["release_commit"], "cross_database_atomic": False, "databases": {}}
    try:
        for name, source in cfg["databases"].items():
            target = dest / DATABASES[name]
            write_new(target, b"")
            deadline = time.monotonic() + timeout
            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise Blocked("SQLite backup exceeded deadline")
            src = sqlite3.connect(Path(source).as_uri() + "?mode=ro", uri=True, timeout=5)
            dst = sqlite3.connect(target, timeout=5)
            try:
                src.execute("PRAGMA query_only=ON")
                src.backup(dst, pages=128, progress=progress, sleep=0.05)
                # Produce a self-contained backup, independent of source WAL sidecars.
                dst.execute("PRAGMA journal_mode=DELETE")
            finally:
                dst.close()
                src.close()
            check_database(target)
            manifest["databases"][name] = {"file": target.name, "sha256": digest(target), "bytes": target.stat().st_size}
        manifest["finished_at"] = utcnow()
        write_new(dest / "manifest.json", manifest)
        return dest
    except BaseException:
        shutil.rmtree(dest)
        raise


def restore_to_empty(cfg, backup_path, destination):
    source = contained(Path(backup_path), Path(cfg["envroot"]) / "backups")
    target = contained(Path(destination), Path(cfg["envroot"]) / "restore-drills")
    if target.exists():
        raise Blocked("restore destination must not exist; live DB overwrite is forbidden")
    manifest = read_json(source / "manifest.json")
    if manifest["environment"] != cfg["environment"] or set(manifest["databases"]) != set(DATABASES):
        raise Blocked("backup environment/domain mismatch")
    for name, entry in manifest["databases"].items():
        if entry["file"] != DATABASES[name]:
            raise Blocked("invalid backup filename")
        db = contained(source / entry["file"], source)
        if digest(db) != entry["sha256"]:
            raise Blocked("backup checksum mismatch")
        check_database(db)
    private_dir(target)
    try:
        for name, entry in manifest["databases"].items():
            dest = target / name / DATABASES[name]
            copy_new(source / entry["file"], dest)
            check_database(dest)
        write_new(target / "restore-manifest.json", {"restored_at": utcnow(), "backup": str(source),
                                                   "live_data_replaced": False})
    except BaseException:
        shutil.rmtree(target)
        raise
    return target


def expanded(argv, cfg):
    replacements = {"{release}": cfg["release_path"], "{environment}": cfg["envroot"]}
    result = []
    for value in argv:
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        result.append(value)
    return result


def render(cfg, cfgpath, output, daemon_user=None):
    out = contained(Path(output), Path(cfg["envroot"]) / "plans")
    if out.exists():
        raise Blocked("render output must not exist")
    if daemon_user and (daemon_user == "root" or not re.fullmatch(r"[a-z_][a-z0-9_-]*", daemon_user)):
        raise Blocked("launchd services require a nonroot user")
    launcher = out / "runtime" / "release_ops.py"
    write_new(launcher, Path(__file__).read_bytes())
    for name in SERVICES:
        logfile = Path(cfg["envroot"]) / "logs" / (name + ".log")
        spec = {"Label": "ca.ikun.v2." + cfg["environment"] + "." + name,
                "ProgramArguments": [sys.executable, str(launcher), "run-service", "--config",
                                     str(Path(cfgpath).absolute()), "--service", name],
                "WorkingDirectory": cfg["release_path"], "RunAtLoad": True, "KeepAlive": True,
                "ThrottleInterval": 30, "ExitTimeOut": 30, "ProcessType": "Background", "Nice": 5,
                "Umask": 0o077, "StandardOutPath": str(logfile), "StandardErrorPath": str(logfile),
                "SoftResourceLimits": {"NumberOfFiles": 1024}}
        if cfg["environment"] == "production":
            spec["ProgramArguments"] += ["--approval", str(Path(cfg["envroot"]) / "config" / "publish.approval.json")]
        if daemon_user:
            spec["UserName"] = daemon_user
        write_new(out / (spec["Label"] + ".plist"), plistlib.dumps(spec))
    write_new(out / "plan.json", {"environment": cfg["environment"], "generated_at": utcnow(),
                                 "installed": False, "started": False, "dns_changed": False,
                                 "launchd_scope": "system" if daemon_user else "gui",
                                 "release_commit": cfg["release_commit"]})
    return out


def publish_approval(cfg, cfgpath, approval):
    if cfg["environment"] != "production":
        return
    if not approval or not Path(approval).is_file():
        raise Blocked("production publication requires explicit user approval, recorded by the operator")
    if Path(approval).is_symlink() or Path(approval).stat().st_mode & 0o077:
        raise Blocked("approval file must be private and must not be a symlink")
    record = read_json(approval)
    if (record.get("operation") != "publish_production" or record.get("release_commit") != cfg["release_commit"]
            or record.get("config_sha256") != digest(cfgpath) or record.get("approved_by") != "user"):
        raise Blocked("production approval does not bind this exact release/configuration")


def service_environment(cfg, name):
    spec = cfg["services"][name]
    secret = Path(spec["environment_file"])
    if not secret.is_file() or secret.stat().st_mode & 0o077:
        raise Blocked("private per-service environment JSON is required (chmod 600)")
    values = read_json(secret)
    values.update(spec.get("environment", {}))
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
        raise Blocked("environment keys and values must be strings")
    if any(k.startswith("NEXT_PUBLIC_") for k in values):
        raise Blocked("deployment secrets must never be exposed through NEXT_PUBLIC_ variables")
    env = {k: os.environ[k] for k in ("HOME", "LANG", "TMPDIR") if k in os.environ}
    env.update({"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin", "TZ": "Asia/Shanghai",
                "NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1", "HOSTNAME": "127.0.0.1",
                "PORT": str(spec["port"]), "UV_THREADPOOL_SIZE": "2",
                "NODE_OPTIONS": "--max-old-space-size=" + ("768" if name == "web" else "256"),
                "IKUN_ENV_FILE": str(Path(cfg["envroot"]) / "config" / "no-dotenv")})
    env.update(values)
    if env.get("NODE_ENV") != "production" or env.get("HOSTNAME") != "127.0.0.1":
        raise Blocked("production mode and loopback cannot be overridden")
    if cfg["environment"] == "staging" and env.get("IKUN_REMOTE_ENABLED", "false") != "false":
        raise Blocked("staging must not mutate remote Watch")
    return env


def run_service(cfg, cfgpath, name, approval=None):
    publish_approval(cfg, cfgpath, approval)
    commit = git(cfg["release_path"], "rev-parse", "HEAD")
    if commit != cfg["release_commit"] or git(cfg["release_path"], "status", "--porcelain"):
        raise Blocked("release checkout is missing, dirty or does not match the pinned SHA")
    argv = expanded(cfg["services"][name]["argv"], cfg)
    if not Path(argv[0]).is_file():
        raise Blocked("service executable does not exist")
    env = service_environment(cfg, name)
    if name == "web":
        marker = Path(cfg["services"][name]["build_id_file"].replace("{release}", cfg["release_path"]))
        if not marker.is_file() or not marker.read_text().strip():
            raise Blocked("Next.js production build is required")
        env.setdefault("NODE_OPTIONS", "--max-old-space-size=768")
    for db in cfg["databases"].values():
        private_dir(Path(db).parent)
    private_dir(Path(cfg["envroot"]) / "logs")
    cwd = expanded([cfg["services"][name].get("cwd", "{release}")], cfg)[0]
    if Path(cwd) != Path(cfg["release_path"]):
        contained(Path(cwd), Path(cfg["release_path"]))
    os.chdir(cwd)
    os.execve(argv[0], argv, env)


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, timeout=30,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if proc.returncode:
        raise Blocked("Git operation failed: " + " ".join(args[:2]))
    return proc.stdout.strip()


def intake(manifest_path):
    manifest = read_json(manifest_path)
    repo = Path(manifest["repository"])
    try:
        base = git(repo, "rev-parse", manifest["base_ref"] + "^{commit}")
    except Blocked:
        base = None
    results, files = [], {}
    needed = {"foundation", "ui", "auth", "hunter", "tracking", "homepage"}
    modules = manifest.get("modules", [])
    if {x["name"] for x in modules} != needed or len(modules) != len(needed):
        raise Blocked("manifest must declare exactly the six accepted module handoffs")
    for item in modules:
        issues = []
        if item.get("acceptance") != "ACCEPTED":
            issues.append("module not accepted")
        resolved = None
        if item.get("ref"):
            try:
                resolved = git(repo, "rev-parse", item["ref"] + "^{commit}")
            except Blocked:
                issues.append("branch/tag unavailable")
            if resolved != item.get("commit"):
                issues.append("ref does not match pinned commit")
        else:
            issues.append("missing branch/tag")
        report = item.get("report_path")
        if not report or not Path(report).is_file():
            issues.append("missing acceptance report")
        elif not item.get("report_sha256") or digest(report) != item["report_sha256"]:
            issues.append("report hash mismatch")
        if resolved and base:
            for filename in git(repo, "diff", "--name-only", base, resolved).splitlines():
                files.setdefault(filename, []).append(item["name"])
        results.append({"name": item["name"], "commit": resolved, "blockers": issues})
    return {"checked_at": utcnow(), "base_commit": base,
            "status": "READY_FOR_ISOLATED_MERGE" if base and not any(x["blockers"] for x in results) else "BLOCKED",
            "repository_blockers": [] if base else ["base branch has no committed foundation"],
            "modules": results, "overlapping_files": {k: v for k, v in files.items() if len(v) > 1},
            "production_approved": False}


def assemble(manifest_path, destination):
    decision = intake(manifest_path)
    if decision["status"] != "READY_FOR_ISOLATED_MERGE":
        raise Blocked("unaccepted/missing module handoffs cannot be merged")
    manifest = read_json(manifest_path)
    dest = Path(destination).absolute()
    if dest.exists() or "isolated-merge" not in dest.parts:
        raise Blocked("use a new destination beneath isolated-merge")
    for parent in dest.parents:
        if parent.is_symlink():
            raise Blocked("symlink merge destination")
    clone = subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--no-checkout",
                            str(Path(manifest["repository"]).absolute()), str(dest)], capture_output=True, timeout=60)
    if clone.returncode:
        raise Blocked("isolated clone failed")
    git(dest, "checkout", "-b", "codex/ikun-ca-v2-final-integration", decision["base_commit"])
    for name, value in (("user.name", "Codex Integration"), ("user.email", "integration@localhost")):
        git(dest, "config", name, value)
    for module in decision["modules"]:
        # Do not auto-resolve semantic conflicts. Preserve clone for review.
        git(dest, "merge", "--no-ff", "--no-edit", module["commit"])
    decision["merged_commit"] = git(dest, "rev-parse", "HEAD")
    decision["status"] = "MERGED_PENDING_INTEGRATION_TESTS"
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "render", "backup", "restore-drill", "run-service", "intake", "assemble"))
    parser.add_argument("--config")
    parser.add_argument("--manifest")
    parser.add_argument("--output")
    parser.add_argument("--backup")
    parser.add_argument("--service", choices=SERVICES)
    parser.add_argument("--daemon-user")
    parser.add_argument("--approval")
    args = parser.parse_args()
    try:
        if args.action in ("intake", "assemble"):
            if not args.manifest:
                raise Blocked("--manifest is required")
            result = intake(args.manifest) if args.action == "intake" else assemble(args.manifest, args.output)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 2 if result["status"] == "BLOCKED" else 0
        if not args.config:
            raise Blocked("--config is required")
        cfg = config(args.config)
        if args.action == "validate":
            print(json.dumps({"status": "CONFIG_VALID", "environment": cfg["environment"],
                              "runtime_verified": False, "production_approved": False}))
        elif args.action == "render":
            print(render(cfg, args.config, args.output, args.daemon_user))
        elif args.action == "backup":
            print(backup(cfg))
        elif args.action == "restore-drill":
            print(restore_to_empty(cfg, args.backup, args.output))
        elif args.action == "run-service":
            if not args.service:
                raise Blocked("--service is required")
            run_service(cfg, args.config, args.service, args.approval)
        return 0
    except (Blocked, OSError, KeyError, TypeError, sqlite3.Error, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        # Never echo arbitrary config, environment values, subprocess output or secrets.
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, Blocked) else "invalid/missing local input or timed-out operation"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
