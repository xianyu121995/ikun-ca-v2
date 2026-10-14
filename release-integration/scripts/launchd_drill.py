#!/usr/bin/env python3
"""Exercise three harmless staging jobs. Never load production/legacy labels."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import release_ops as ops

FIXTURE = '''import json, os, signal, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
runid, role, port = sys.argv[1:]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        body = json.dumps({"fixture": True, "run_id": runid, "role": role, "pid": os.getpid()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
server = HTTPServer(("127.0.0.1", int(port)), Handler)
server.serve_forever(poll_interval=0.25)
'''


def launchctl(*args, must_succeed=True):
    result = subprocess.run(["/bin/launchctl", *args], text=True, capture_output=True, timeout=15)
    if result.returncode and must_succeed:
        raise ops.Blocked("launchctl " + args[0] + " failed; no legacy jobs touched")
    return result


def wait_absent(target, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launchctl("print", target, must_succeed=False).returncode != 0:
            return True
        time.sleep(0.2)
    return False


def ready(port, runid, timeout=45, previous=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:" + str(port) + "/health", timeout=1) as response:
                result = json.load(response)
            if result.get("run_id") == runid and result["pid"] != previous:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise ops.Blocked("fixture readiness/recovery deadline exceeded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise ops.Blocked("native macOS launchd is required")
    runid = uuid.uuid4().hex[:12]
    root = Path(tempfile.mkdtemp(prefix="ikun-ca-v2-launchd-", dir="/private/tmp"))
    ops.private_dir(root)
    fixture = root / "fixture.py"
    ops.write_new(fixture, FIXTURE.encode())
    jobs, loaded = {}, []
    domain = "gui/" + str(os.getuid())
    report = {"run_id": runid, "started_at": ops.utcnow(), "fixture_only": True,
              "business_flow_verified": False, "production_services_modified": False,
              "runtime_path": str(root), "status": "FAIL"}
    try:
        for role in ops.SERVICES:
            with socket.socket() as candidate:
                candidate.bind(("127.0.0.1", 0))
                port = candidate.getsockname()[1]
            label = "ca.ikun.v2.drill." + runid + "." + role
            assert re.fullmatch(r"ca\.ikun\.v2\.drill\.[a-f0-9]{12}\.(web|hunter|tracking)", label)
            path = root / (label + ".plist")
            content = {"Label": label, "ProgramArguments": [sys.executable, str(fixture), runid, role, str(port)],
                       "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10, "ExitTimeOut": 10,
                       "WorkingDirectory": str(root), "Umask": 0o077,
                       "StandardOutPath": str(root / (role + ".log")),
                       "StandardErrorPath": str(root / (role + ".log"))}
            ops.write_new(path, plistlib.dumps(content))
            launchctl("bootstrap", domain, str(path))
            loaded.append(label)
            jobs[role] = {"label": label, "port": port, "initial": ready(port, runid)}
        if len({x["initial"]["pid"] for x in jobs.values()}) != 3:
            raise ops.Blocked("fixtures are not three independent processes")
        # Keep first launch alive beyond launchd's documented 10-second crash threshold.
        time.sleep(10)
        for role in ops.SERVICES:
            launchctl("kill", "SIGKILL", domain + "/" + jobs[role]["label"])
            after = ready(jobs[role]["port"], runid, previous=jobs[role]["initial"]["pid"])
            jobs[role]["restarted"] = after
            for other in ops.SERVICES:
                expected = jobs[other].get("restarted", jobs[other]["initial"])["pid"]
                if ready(jobs[other]["port"], runid)["pid"] != expected:
                    raise ops.Blocked("another fixture restarted unexpectedly")
        report.update({"status": "PASS", "three_independent_pids": True,
                       "website_restart_does_not_restart_workers": True, "jobs": jobs})
    finally:
        cleanup = {}
        for label in reversed(loaded):
            result = launchctl("bootout", domain + "/" + label, must_succeed=False)
            absent = wait_absent(domain + "/" + label)
            cleanup[label] = {"bootout_returncode": result.returncode, "job_absent": absent}
        report["cleanup"] = cleanup
        report["finished_at"] = ops.utcnow()
        if cleanup and not all(x["job_absent"] for x in cleanup.values()):
            report["status"] = "FAIL_CLEANUP"
        ops.write_new(Path(args.output).absolute(), report)
    print(json.dumps({"report": str(Path(args.output).absolute()), "status": report.get("status", "FAIL")}))
    if report.get("status") != "PASS":
        raise ops.Blocked("launchd drill failed or cleanup incomplete")


if __name__ == "__main__":
    try:
        main()
    except (ops.Blocked, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc) if isinstance(exc, ops.Blocked)
                          else "native drill failed"}), file=sys.stderr)
        sys.exit(2)
