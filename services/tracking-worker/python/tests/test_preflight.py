"""Read-only admission checks using isolated release/Tracking DB and actual local metadata."""

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracking.store import Store


@pytest.fixture
def admission(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]
    root = tmp_path.resolve() / "owned"
    root.mkdir(mode=0o700)
    release = root / "releases" / ("a" * 40)
    module = release / "services/tracking-worker/python"
    (module / "integration").mkdir(parents=True)
    for name in ("entry.py", "requirements.lock.txt"):
        shutil.copyfile(source / name, module / name)
    shutil.copytree(source / "tracking", module / "tracking", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(source.parents[2] / "schemas/tracking", release / "schemas/tracking")
    script = module / "integration/preflight-release.py"
    shutil.copyfile(source / "integration/preflight-release.py", script)
    (root / "venvs").mkdir(mode=0o700)
    venv = root / "venvs/tracking"
    venv.mkdir(mode=0o700)
    (venv / "bin").mkdir(mode=0o700)
    (venv / "bin/python").symlink_to(Path(sys.executable).resolve())
    legacy = release / ".venv"
    legacy.mkdir(mode=0o700)
    job = root / "job"
    job.mkdir(mode=0o700)
    config_dir = root / "config"
    config_dir.mkdir(mode=0o700)
    config = config_dir / "tracking.json"
    db = root / "data/tracking/tracking.db"
    Store(db, initialize=True)
    config.write_text(json.dumps({"db_path": str(db), "remote_enabled": False, "dedicated_account": False}))
    config.chmod(0o600)
    monkeypatch.delenv("IKUN_TRACKING_6551_TOKEN", raising=False)
    monkeypatch.delenv("DATA_ROOT", raising=False)
    monkeypatch.setenv("TRACKING_API_TOKEN", "preflight-fixture-direction-xxxxxxxxxxx")
    # Load actual release modules; do not mock their source paths or inspect implementation.
    original_modules = {
        key: value for key, value in sys.modules.items() if key == "tracking" or key.startswith("tracking.")
    }
    original_path, original_bytecode = sys.path[:], sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    for name in original_modules:
        del sys.modules[name]
    try:
        spec = importlib.util.spec_from_file_location("release_preflight", script)
        preflight = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preflight)
        monkeypatch.setattr(sys, "prefix", str(venv))
        yield SimpleNamespace(
            root=root,
            release=release,
            module=module,
            job=job,
            config=config,
            db=db,
            venv=venv,
            legacy=legacy,
            preflight=preflight,
        )
    finally:
        for name in list(sys.modules):
            if name == "tracking" or name.startswith("tracking."):
                del sys.modules[name]
        sys.modules.update(original_modules)
        sys.path[:] = original_path
        sys.dont_write_bytecode = original_bytecode


def run(env, venv=True):
    return env.preflight.preflight(env.release, env.job, env.config, env.venv if venv else None)


def test_explicit_owned_venv_accepts_managed_interpreter_link_without_writes(admission):
    env = admission
    files = [env.db, env.config, *env.module.rglob("*.py"), env.module / "requirements.lock.txt"]
    before = {p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
    result = run(env)
    assert result["passed"] and result["venv_root"] == str(env.venv)
    assert result["database_ddl_executed"] is False and result["provider_calls"] == 0
    assert result["pinned_dependency_count"] == 25
    assert (env.venv / "bin/python").is_symlink()
    assert not (env.venv / "bin/python").resolve().is_relative_to(env.venv)
    assert before == {p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
    assert not list(env.module.rglob("__pycache__"))


def test_no_argument_preserves_release_internal_venv(admission, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(admission.legacy))
    assert run(admission, venv=False)["passed"]


@pytest.mark.parametrize("relative", ["venvs/hunter", "venvs/tracking2", "venv/tracking", "releases/other"])
def test_wrong_service_or_layout_is_rejected(admission, monkeypatch, relative):
    candidate = admission.root / relative
    candidate.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(sys, "prefix", str(candidate))
    with pytest.raises(ValueError, match="exact owned Tracking"):
        admission.preflight.preflight(admission.release, admission.job, admission.config, candidate)


@pytest.mark.parametrize("kind", ["relative", "dotdot", "dot", "trailing"])
def test_explicit_venv_path_aliases_rejected(admission, kind):
    value = {
        "relative": "venvs/tracking",
        "dotdot": str(admission.venv / "../tracking"),
        "dot": str(admission.root) + "/venvs/./tracking",
        "trailing": str(admission.venv) + "/",
    }[kind]
    with pytest.raises(ValueError, match="nonaliased"):
        admission.preflight.preflight(admission.release, admission.job, admission.config, value)


@pytest.mark.parametrize("level", ["root", "venvs", "tracking"])
def test_directory_symlinks_at_each_venv_level_rejected(admission, monkeypatch, level):
    env = admission
    if level == "root":
        alias = env.root.parent / "owned-alias"
        alias.symlink_to(env.root, target_is_directory=True)
        candidate = alias / "venvs/tracking"
    else:
        target = env.root / "venvs" if level == "venvs" else env.venv
        moved = target.with_name(target.name + "-real")
        target.rename(moved)
        target.symlink_to(moved, target_is_directory=True)
        candidate = env.venv
    monkeypatch.setattr(sys, "prefix", str(candidate))
    with pytest.raises(ValueError, match="aliases"):
        env.preflight.preflight(env.release, env.job, env.config, candidate)


@pytest.mark.parametrize("where", ["root", "venvs", "venv", "job", "config_dir", "config"])
def test_nonprivate_paths_rejected(admission, where):
    paths = {
        "root": admission.root,
        "venvs": admission.root / "venvs",
        "venv": admission.venv,
        "job": admission.job,
        "config_dir": admission.config.parent,
        "config": admission.config,
    }
    paths[where].chmod(0o644 if where == "config" else 0o755)
    with pytest.raises(ValueError, match="private"):
        run(admission)


@pytest.mark.parametrize("prefix", ["relative", "other", "legacy-without-argument"])
def test_actual_prefix_must_match_selected_venv(admission, monkeypatch, prefix):
    candidate = {
        "relative": "venvs/tracking",
        "other": str(admission.legacy),
        "legacy-without-argument": str(admission.venv),
    }[prefix]
    monkeypatch.setattr(sys, "prefix", candidate)
    with pytest.raises(ValueError):
        run(admission, venv=prefix != "legacy-without-argument")


@pytest.mark.parametrize("name", ["entry.py", "requirements.lock.txt"])
def test_reviewed_file_bytes_are_pinned(admission, name):
    path = admission.module / name
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="approved manifest"):
        run(admission)


@pytest.mark.parametrize("mode", ["missing", "wrong"])
def test_missing_or_wrong_pinned_dependency_rejected(admission, monkeypatch, mode):
    metadata = admission.preflight.importlib.metadata
    actual = metadata.version

    def version(name):
        if name == "Pygments":
            if mode == "missing":
                raise metadata.PackageNotFoundError(name)
            return "0.0"
        return actual(name)

    monkeypatch.setattr(metadata, "version", version)
    with pytest.raises(ValueError, match="pinned dependency"):
        run(admission)


@pytest.mark.parametrize("origin", ["self", "config", "migration"])
def test_preflight_and_imports_cannot_escape_release(admission, monkeypatch, origin):
    module = {
        "self": admission.preflight,
        "config": admission.preflight.config_module,
        "migration": admission.preflight.migration,
    }[origin]
    monkeypatch.setattr(module, "__file__", __file__)
    with pytest.raises(ValueError, match="admitted release"):
        run(admission)


@pytest.mark.parametrize("name", [".env", ".env.production.local"])
def test_implicit_environment_files_rejected(admission, name):
    (admission.job / name).write_text("FIXTURE=1\n")
    with pytest.raises(ValueError, match="environment files"):
        run(admission)


@pytest.mark.parametrize("field", ["remote_enabled", "dedicated_account", "token_file"])
def test_external_collection_remains_disabled(admission, field):
    config = json.loads(admission.config.read_text())
    config[field] = "unused-provider-file" if field == "token_file" else True
    admission.config.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="external collection"):
        run(admission)


def test_missing_direction_credential_rejected(admission, monkeypatch):
    monkeypatch.delenv("TRACKING_API_TOKEN")
    with pytest.raises(ValueError, match="direction credential"):
        run(admission)


def test_foreign_tracking_database_rejected_without_mutation(admission):
    import sqlite3

    with sqlite3.connect(admission.db) as db:
        db.execute("PRAGMA application_id=1")
    before = admission.db.read_bytes()
    with pytest.raises(ValueError, match="foreign database"):
        run(admission)
    assert admission.db.read_bytes() == before
