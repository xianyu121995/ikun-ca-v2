"""Read-only release admission. Does not init/migrate, start services or contact a provider."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracking import config as config_module
from tracking import migration

# Approved B3 manifest f3bc195; this admission-only delta does not change either file.
APPROVED_FILES = {
    "entry.py": "f936a4b18add4568356539f5499c482900f81286910ec3e6180633a4961082e6",
    "requirements.lock.txt": "89cb0cca8c57c2e4a12d9947a9c6e5924ce10aefa163554640cf74f09c6e3287",
}


def canonical(value):
    raw = os.fspath(value)
    path = Path(raw)
    if not path.is_absolute() or raw != str(path) or ".." in path.parts:
        raise ValueError("absolute nonaliased paths required")
    if any(p.is_symlink() for p in (path, *path.parents)) or path != path.resolve(strict=True):
        raise ValueError("release aliases rejected")
    return path


def private(path, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not directory
        and info.st_nlink != 1
    ):
        raise ValueError("private owned directory/config required")


def preflight(release, job_cwd, config, venv_root=None):
    release, job_cwd, config = [canonical(p) for p in (release, job_cwd, config)]
    if any(part in (".b3", ".preview", "ikun-ca-v2-worktrees") for part in release.parts):
        raise ValueError("runtime must use a standalone release")
    prefix = canonical(sys.prefix)
    if venv_root is None:
        if not prefix.is_relative_to(release):
            raise ValueError("Python dependencies must be installed in the standalone release")
    else:
        venv_root = canonical(venv_root)
        owned_root = release.parent.parent
        if venv_root != owned_root / "venvs/tracking" or prefix != venv_root:
            raise ValueError("exact owned Tracking venv and sys.prefix required")
        for folder in (owned_root, owned_root / "venvs", venv_root):
            private(folder, directory=True)
    module = release / "services/tracking-worker/python"
    for actual, expected in (
        (__file__, module / "integration/preflight-release.py"),
        (config_module.__file__, module / "tracking/config.py"),
        (migration.__file__, module / "tracking/migration.py"),
    ):
        if canonical(actual) != expected:
            raise ValueError("preflight and Tracking imports must use the admitted release")
    digests = {}
    for name, approved in APPROVED_FILES.items():
        path = canonical(module / name)
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("release source or lock must be a regular unaliased file")
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if digests[name] != approved:
            raise ValueError("release source/lock differs from approved manifest")
    if not canonical(module / "tracking/cli.py").is_file():
        raise ValueError("release CLI source missing")
    installed = {}
    for line in (module / "requirements.lock.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, pinned = line.split("==")
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            raise ValueError("pinned dependency is not installed: " + name) from None
        if installed[name] != pinned:
            raise ValueError("pinned dependency version mismatch: " + name)
    for folder in (job_cwd, config.parent):
        for name in (".env", ".env.local", ".env.production", ".env.production.local"):
            if (folder / name).exists() or (folder / name).is_symlink():
                raise ValueError("job cwd must not load environment files")
    private(config)
    private(config.parent, directory=True)
    private(job_cwd, directory=True)
    cfg = config_module.Config.load(str(config))
    if (
        cfg.remote_enabled
        or cfg.dedicated_account
        or cfg.token_file
        or os.environ.get("IKUN_TRACKING_6551_TOKEN")
    ):
        raise ValueError("external collection must be explicitly disabled")
    if cfg.service_token_file:
        private(canonical(cfg.service_token_file))
    service = cfg.secret("service_token")
    if len(service) < 32:
        raise ValueError("independent service direction credential required")
    migration.inspect(cfg.db_path)
    return {
        "passed": True,
        "external_collection_enabled": False,
        "source_state": "unconfigured",
        "migration_checksums": migration.hashes(),
        "python": sys.version.split()[0],
        "venv_root": str(prefix),
        "entry_sha256": digests["entry.py"],
        "dependency_lock_sha256": digests["requirements.lock.txt"],
        "pinned_dependency_count": len(installed),
        "installed_pinned_versions": installed,
        "runtime_uses_worktree": False,
        "database_ddl_executed": False,
        "provider_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--job-cwd", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--venv-root", help="explicit absolute owned-root/venvs/tracking")
    args = parser.parse_args()
    print(json.dumps(preflight(args.release_root, args.job_cwd, args.config, args.venv_root), indent=2))
