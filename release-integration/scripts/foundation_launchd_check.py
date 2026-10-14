#!/usr/bin/env python3
"""Test a frozen idle foundation build under native launchd, never production."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

import release_ops as ops
from launchd_drill import launchctl, wait_absent


def fetch(port, path):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            "http://127.0.0.1:" + str(port) + path, timeout=2) as response:
        return response.status, json.load(response)


def wait_ready(port, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, response = fetch(port, "/health/ready")
            if status == 200:
                return response
        except (OSError, ValueError):
            pass
        time.sleep(0.3)
    raise ops.Blocked("foundation service did not become ready")


def job_pid(target):
    value = launchctl("print", target).stdout
    match = re.search(r"\n\s*pid = (\d+)", value)
    if not match:
        raise ops.Blocked("launchd service has no running PID")
    return int(match.group(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.worktree).absolute()
    commit = ops.git(source, "rev-parse", "HEAD")
    if commit != ops.git(source, "rev-parse", "foundation-v0.1.0") or ops.git(source, "diff", "--name-only", "HEAD"):
        raise ops.Blocked("this drill accepts only the unchanged frozen foundation")
    parent = Path(tempfile.mkdtemp(prefix="ikun-v2-foundation-", dir="/private/tmp"))
    root = parent / "ikun-ca-v2-deployment"
    release = root / "releases" / commit
    release.parent.mkdir(parents=True)
    result = subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--no-checkout", str(source), str(release)],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ops.Blocked("frozen foundation clone failed")
    ops.git(release, "checkout", "--detach", commit)
    # Package this integration Worktree's already-built dependencies/artifacts, never another Worktree's.
    paths = ["node_modules", "packages/contracts/dist", "packages/runtime/dist", "packages/contracts/node_modules",
             "packages/runtime/node_modules", "services/hunter-worker/dist", "services/hunter-worker/node_modules",
             "services/tracking-worker/dist", "services/tracking-worker/node_modules", "apps/website/.next",
             "apps/website/node_modules"]
    for relative in paths:
        original = source / relative
        if not original.is_dir():
            if relative.endswith("/node_modules"):
                continue  # A dependency-free workspace has no local node_modules directory.
            raise ops.Blocked("build all foundation packages before this drill")
        shutil.copytree(original, release / relative, symlinks=True)
    for path in release.rglob("*"):
        if path.is_symlink() and release not in path.resolve().parents:
            raise ops.Blocked("packaged dependency resolves outside the release")
    node = root / "toolchains" / "node24" / "node"
    ops.copy_new(args.node, node)
    node.chmod(0o700)
    version = subprocess.run([str(node), "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
    if not version.startswith("v24."):
        raise ops.Blocked("Node 24 LTS required")
    prepared = subprocess.run([sys.executable, str(Path(__file__).with_name("prepare_config.py")), "--root", str(root),
                               "--commit", commit, "--node", str(node), "--environment", "staging"],
                              text=True, capture_output=True, timeout=10)
    if prepared.returncode:
        raise ops.Blocked("staging configuration preparation failed")
    cfgpath = root / "staging" / "config" / "release.local.json"
    cfg = ops.config(cfgpath)
    tokens = {name: secrets.token_urlsafe(32) for name in ("HUNTER_API_TOKEN", "TRACKING_API_TOKEN",
                                                        "PROJECTS_INGEST_HUNTER_TOKEN", "PROJECTS_INGEST_TRACKING_TOKEN")}
    for name in ops.SERVICES:
        secret = Path(cfg["services"][name]["environment_file"])
        if name == "web":
            values = {k: v for k, v in tokens.items() if k.startswith("PROJECTS_INGEST_")}
        else:
            key = name.upper() + "_API_TOKEN"
            values = {key: tokens[key]}
        secret.write_text(json.dumps(values))
        secret.chmod(0o600)
    domain = "gui/" + str(os.getuid())
    labels = {name: "ca.ikun.v2.staging." + name for name in ops.SERVICES}
    for name, label in labels.items():
        if launchctl("print", domain + "/" + label, must_succeed=False).returncode == 0:
            raise ops.Blocked("staging label already exists; do not touch another run")
        with socket.socket() as check:
            check.bind(("127.0.0.1", cfg["services"][name]["port"]))
    plan = ops.render(cfg, cfgpath, root / "staging" / "plans" / "native-foundation")
    for path in cfg["databases"].values():
        ops.private_dir(Path(path).parent)
    ops.private_dir(root / "staging" / "logs")
    report = {"started_at": ops.utcnow(), "foundation_commit": commit, "node_version": version,
              "node_sha256": ops.digest(node), "idle_foundation_only": True, "business_flow_verified": False,
              "production_services_modified": False, "runtime_path": str(root), "status": "FAIL", "checks": []}
    loaded = []
    try:
        for name, label in labels.items():
            launchctl("bootstrap", domain, str(plan / (label + ".plist")))
            loaded.append(label)
            wait_ready(cfg["services"][name]["port"])
        pids = {name: job_pid(domain + "/" + label) for name, label in labels.items()}
        if len(set(pids.values())) != 3:
            raise ops.Blocked("three distinct service PIDs required")
        report["initial_pids"] = pids.copy()
        report["checks"].append("three_primary_processes")
        identities = {}
        for name, path in cfg["databases"].items():
            ops.check_database(path)
            with sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True) as con:
                identities[name] = {"inode": Path(path).stat().st_ino,
                                    "application_id": con.execute("PRAGMA application_id").fetchone()[0],
                                    "store_name": con.execute("SELECT store_name FROM _store_identity").fetchone()[0]}
        if len({x["inode"] for x in identities.values()}) != 4 or any(x["store_name"] != k for k, x in identities.items()):
            raise ops.Blocked("physical domain isolation failed")
        report["databases"] = identities
        report["checks"].append("four_owned_separate_database_files")
        time.sleep(10)
        for name, label in labels.items():
            start = time.monotonic()
            launchctl("kill", "SIGKILL", domain + "/" + label)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    newpid = job_pid(domain + "/" + label)
                    if newpid != pids[name]:
                        wait_ready(cfg["services"][name]["port"], timeout=10)
                        break
                except ops.Blocked:
                    pass
                time.sleep(0.3)
            else:
                raise ops.Blocked("foundation restart exceeded deadline")
            for other, otherlabel in labels.items():
                if other != name and job_pid(domain + "/" + otherlabel) != pids[other]:
                    raise ops.Blocked("another foundation service restarted unexpectedly")
                wait_ready(cfg["services"][other]["port"], timeout=5)
            report.setdefault("recovery", {})[name] = {"old_pid": pids[name], "new_pid": newpid,
                                                        "elapsed_seconds": round(time.monotonic() - start, 3)}
            pids[name] = newpid
        snapshot = ops.backup(cfg)
        restored = ops.restore_to_empty(cfg, snapshot, root / "staging" / "restore-drills" / "foundation")
        report["backup_restore_drill"] = {"backup": str(snapshot), "restored": str(restored), "live_data_replaced": False}
        report["checks"] += ["each_service_recovers_without_restarting_others", "foundation_sqlite_backup_restore"]
        report["status"] = "PASS"
    finally:
        report["cleanup"] = {}
        for label in reversed(loaded):
            launchctl("bootout", domain + "/" + label, must_succeed=False)
            report["cleanup"][label] = wait_absent(domain + "/" + label)
        if loaded and not all(report["cleanup"].values()):
            report["status"] = "FAIL_CLEANUP"
        report["finished_at"] = ops.utcnow()
        ops.write_new(Path(args.output).absolute(), report)
    print(json.dumps({"report": str(Path(args.output).absolute()), "status": report["status"],
                      "business_flow_verified": False}))
    if report["status"] != "PASS":
        raise ops.Blocked("foundation native verification failed")


if __name__ == "__main__":
    try:
        main()
    except (ops.Blocked, OSError, subprocess.TimeoutExpired, sqlite3.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc) if isinstance(exc, ops.Blocked)
                          else "native foundation check failed"}), file=sys.stderr)
        sys.exit(2)
