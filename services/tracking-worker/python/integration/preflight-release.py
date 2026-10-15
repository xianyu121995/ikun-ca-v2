"""Read-only release admission. Does not init/migrate, start services or contact a provider."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracking.config import Config  # noqa: E402
from tracking.migration import hashes, inspect  # noqa: E402


def preflight(release, job_cwd, config):
    release, job_cwd, config = [Path(p).absolute() for p in (release, job_cwd, config)]
    for path in (release, job_cwd, config):
        if path != path.resolve():
            raise ValueError("release aliases rejected")
    if any(part in (".b3", ".preview", "ikun-ca-v2-worktrees") for part in release.parts):
        raise ValueError("runtime must use a standalone release")
    for folder in (job_cwd, config.parent):
        for name in (".env", ".env.local", ".env.production", ".env.production.local"):
            if (folder / name).exists():
                raise ValueError("job cwd must not load environment files")
    if config.stat().st_mode & 0o077 or job_cwd.stat().st_mode & 0o077:
        raise ValueError("private job/config permissions required")
    cfg = Config.load(str(config))
    if (
        cfg.remote_enabled
        or cfg.dedicated_account
        or cfg.token_file
        or os.environ.get("IKUN_TRACKING_6551_TOKEN")
    ):
        raise ValueError("external collection must be explicitly disabled")
    service = cfg.secret("service_token")
    if len(service) < 32:
        raise ValueError("independent service direction credential required")
    if not Path(sys.prefix).absolute().is_relative_to(release):
        raise ValueError("Python dependencies must be installed in the standalone release")
    module = release / "services/tracking-worker/python"
    if Path(__file__).resolve() != module / "integration/preflight-release.py":
        raise ValueError("preflight itself must run from the admitted release")
    for name in ("entry.py", "tracking/cli.py", "requirements.lock.txt"):
        if not (module / name).is_file():
            raise ValueError("release source or lock missing")
    inspect(cfg.db_path)
    return {
        "passed": True,
        "external_collection_enabled": False,
        "source_state": "unconfigured",
        "migration_checksums": hashes(),
        "python": sys.version.split()[0],
        "entry_sha256": hashlib.sha256((module / "entry.py").read_bytes()).hexdigest(),
        "dependency_lock_sha256": hashlib.sha256((module / "requirements.lock.txt").read_bytes()).hexdigest(),
        "runtime_uses_worktree": False,
        "database_ddl_executed": False,
        "provider_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--job-cwd", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    print(json.dumps(preflight(args.release_root, args.job_cwd, args.config), indent=2))
