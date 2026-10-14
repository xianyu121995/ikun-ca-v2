#!/usr/bin/env python3
"""Generate review-only v2 deployment configuration; no services or databases started."""
import argparse
import json
from pathlib import Path
import sys

import release_ops as ops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--environment", choices=("staging", "production"), default="staging")
    args = parser.parse_args()
    root = Path(args.root).absolute()
    envroot = root / args.environment
    release = root / "releases" / args.commit
    first_port = 4000 if args.environment == "staging" else 4100
    cfg = {"environment": args.environment, "deployment_root": str(root), "release_path": str(release),
           "release_commit": args.commit,
           "databases": {name: str(envroot / "data" / name / filename) for name, filename in ops.DATABASES.items()},
           "services": {}}
    for index, (service, script) in enumerate((("web", "website"), ("hunter", "hunter"), ("tracking", "tracking"))):
        cfg["services"][service] = {
            "host": "127.0.0.1", "port": (first_port, first_port + 11, first_port + 12)[index],
            "argv": ([str(Path(args.node).absolute()), "{release}/apps/website/node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(first_port)] if service == "web" else [str(Path(args.node).absolute()), "{release}/services/" + service + "-worker/dist/main.js"]),
            "cwd": "{release}/apps/website" if service == "web" else "{release}",
            "environment_file": str(envroot / "config" / (service + ".secret.json")),
            "environment": {"IKUN_ENV": args.environment, "IKUN_REMOTE_ENABLED": "false",
                            "DATA_ROOT": str(envroot / "data"), "WEBSITE_HOST": "127.0.0.1",
                            "WEBSITE_PORT": str(first_port), "HUNTER_PORT": str(first_port + 11),
                            "TRACKING_PORT": str(first_port + 12), "HUNTER_API_URL": "http://127.0.0.1:" + str(first_port + 11),
                            "TRACKING_API_URL": "http://127.0.0.1:" + str(first_port + 12)},
        }
    cfg["services"]["web"]["build_id_file"] = "{release}/apps/website/.next/BUILD_ID"
    path = envroot / "config" / "release.local.json"
    # Validate before writing; no fake placeholder commit or implicit business DB creation.
    if root.name != "ikun-ca-v2-deployment" or len(args.commit) != 40:
        raise ops.Blocked("use dedicated deployment root and a real 40-character commit")
    ops.write_new(path, cfg)
    try:
        ops.config(path)
    except BaseException:
        path.unlink()
        raise
    for name in ops.SERVICES:
        ops.write_new(envroot / "config" / (name + ".secret.json"), {})
    print(json.dumps({"config": str(path), "business_databases_created": False,
                      "services_started": False, "release_verified": False}))


if __name__ == "__main__":
    try:
        main()
    except (ops.Blocked, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc) if isinstance(exc, ops.Blocked)
                          else "output already exists or cannot be written"}), file=sys.stderr)
        sys.exit(2)
