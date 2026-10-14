#!/usr/bin/env python3
"""Read-only, sanitized Mac/legacy/source baseline; no config or cookie dumps."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
from urllib.parse import urlsplit
import urllib.error
import urllib.request

import release_ops as ops


def command(argv):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=15)
    return result.returncode, result.stdout.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = {"checked_at": ops.utcnow(), "read_only": True, "production_changes": [], "errors": []}
    for key, argv in (("hardware_model", ["/usr/sbin/sysctl", "-n", "hw.model"]),
                      ("memory_bytes", ["/usr/sbin/sysctl", "-n", "hw.memsize"]),
                      ("macos_version", ["/usr/bin/sw_vers", "-productVersion"])):
        status, data = command(argv)
        report[key] = data if status == 0 else None
    status, processes = command(["/bin/ps", "-axo", "pid,ppid,rss,etime,comm"])
    if status == 0:
        report["existing_processes"] = []
        for line in processes.splitlines()[1:]:
            parts = line.split(None, 4)
            if len(parts) == 5 and any(word in parts[4].lower() for word in ("python", "cloudflar", "next", "postgres")):
                report["existing_processes"].append(dict(zip(("pid", "ppid", "rss_kib", "elapsed", "executable"), parts)))
    else:
        report["errors"].append("process inventory unavailable")
    status, listeners = command(["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    report["existing_listeners"] = [line for line in listeners.splitlines()
                                    if line.startswith(("python", "node", "cloudflar", "postgres"))] if status == 0 else None
    report["launch_agents"] = []
    directory = Path.home() / "Library" / "LaunchAgents"
    for path in directory.glob("*.plist"):
        if not any(word in path.name for word in ("ikun", "hunter", "tracking", "cloudflare")):
            continue
        try:
            entry = plistlib.loads(path.read_bytes())
            report["launch_agents"].append({"file": str(path), "label": entry.get("Label"), "sha256": ops.digest(path)})
        except (OSError, ValueError):
            report["errors"].append("one launch agent could not be read")
    repo = Path(args.repository).absolute()
    report["repository"] = str(repo)
    try:
        report["head"] = ops.git(repo, "rev-parse", "HEAD")
        report["branches"] = ops.git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads").splitlines()
    except ops.Blocked:
        report["head"] = None
        report["branches"] = []
    report["git_status"] = ops.git(repo, "status", "--porcelain").splitlines()
    report["protected_legacy_modified_by_this_task"] = False
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(urllib.request.Request("https://ikun.ca", method="HEAD"), timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError):
        response = None
        report["errors"].append("public HTTPS probe unavailable")
    if response:
        with response:
            location = urlsplit(response.headers.get("Location", ""))
            report["public_edge"] = {"status": response.status, "https_certificate_verified": True,
                                     "redirect_host": location.hostname, "redirect_path": location.path,
                                     "cloudflare_access_redirect": response.status in (302, 303, 307)
                                     and (location.hostname or "").endswith(".cloudflareaccess.com"),
                                     "new_origin_verified": False}
    # Record the other client's result too; never expose Set-Cookie or redirect query.
    status, headers = command(["/usr/bin/curl", "--silent", "--show-error", "--max-time", "12", "--head", "https://ikun.ca"])
    if status == 0:
        lines = headers.splitlines()
        http_lines = [line for line in lines if line.startswith("HTTP/")]
        locations = [line.partition(":")[2].strip() for line in lines if line.lower().startswith("location:")]
        location = urlsplit(locations[-1] if locations else "")
        report["curl_public_edge"] = {"status_line": http_lines[-1] if http_lines else None,
                                      "redirect_host": location.hostname, "redirect_path": location.path,
                                      "tls_verified": True, "new_origin_verified": False}
    ops.write_new(Path(args.output).absolute(), report)
    print(json.dumps({"report": str(Path(args.output).absolute()), "repository_head": report["head"],
                      "public_edge": report.get("public_edge"), "errors": report["errors"]}))


if __name__ == "__main__":
    main()
