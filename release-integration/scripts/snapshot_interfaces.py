#!/usr/bin/env python3
"""Pin safe source interface evidence; never read secrets or running databases."""
import argparse
from pathlib import Path
import json
import re

import release_ops as ops

FILES = {
    "foundation_contract": "ikun-ca-v2/packages/contracts/src/index.ts",
    "foundation_architecture": "ikun-ca-v2/docs/ARCHITECTURE.md",
    "website_api": "ikun-ca-v2/apps/website/app/api/v1/[...path]/route.ts",
    "homepage_schema": "ikun-ca-v2/homepage/projects_service/migrations/001_projects.sql",
    "homepage_api": "ikun-ca-v2/homepage/projects_service/api.py",
    "auth_store": "ikun-ca-v2/auth/ikun_auth/store.py",
    "tracking_package": "ikun-ca-v2/tracking/pyproject.toml",
    "hunter_package": "pyproject.toml",
}
PATTERNS = {
    "foundation_contract": r"type Role",
    "foundation_architecture": r"不增加第四个服务|三个独立 OS 进程",
    "website_api": r"AUTH_NOT_CONFIGURED|status: 503",
    "homepage_schema": r"CREATE TABLE (principals|sessions)|role TEXT",
    "homepage_api": r"/api/home/session|PERMISSIONS =|def authenticate",
    "auth_store": r"role TEXT.*superadmin",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.workspace).absolute()
    result = {"checked_at": ops.utcnow(), "uncommitted_source_snapshot": True,
              "release_acceptance": False, "files": {}}
    for key, relative in FILES.items():
        path = root / relative
        if not path.is_file():
            result["files"][key] = {"path": str(path), "exists": False}
            continue
        matches = []
        if key in PATTERNS:
            for index, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(PATTERNS[key], line):
                    matches.append({"line": index, "source": line.strip()})
        result["files"][key] = {"path": str(path), "sha256": ops.digest(path), "matches": matches}
    ops.write_new(Path(args.output).absolute(), result)
    print(json.dumps({"report": str(Path(args.output).absolute()), "release_acceptance": False}))


if __name__ == "__main__":
    main()
