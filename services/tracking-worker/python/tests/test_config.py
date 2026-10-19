import json
from pathlib import Path

import pytest

from tracking.config import Config


@pytest.mark.parametrize("value", ["fixture\ncredential", "fixture secret", "fixture秘密", "x" * 8193])
def test_invalid_secret_has_no_credential_in_error(monkeypatch, value):
    monkeypatch.setenv("TRACKING_API_TOKEN", value)
    with pytest.raises(ValueError, match="invalid service_token credential format") as error:
        Config().secret("service_token")
    assert value not in str(error.value)


def test_example_config_and_data_root_boundary(tmp_path, monkeypatch):
    example = Path(__file__).resolve().parents[1] / "config.example.json"
    raw = json.loads(example.read_text())
    monkeypatch.delenv("DATA_ROOT", raising=False)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(raw))
    cfg = Config.load(str(config))
    assert cfg.db_path == tmp_path / "data/tracking/tracking.db" and not cfg.remote_enabled
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "different"))
    with pytest.raises(ValueError, match="DATA_ROOT"):
        Config.load(str(config))
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    assert Config.load(str(config)).db_path == cfg.db_path


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_timing_config_rejected(tmp_path, value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"reconcile_seconds": value}))
    with pytest.raises(ValueError, match="reconcile_seconds"):
        Config.load(str(path))


def test_secret_file_permissions_relative_paths_and_retired_config(tmp_path):
    secret = tmp_path / "fixture-token"
    secret.write_text("synthetic-file-token\n")
    secret.chmod(0o600)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token_file": "fixture-token"}))
    assert Config.load(str(path)).secret("token") == "synthetic-file-token"
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="mode 600"):
        Config.load(str(path)).secret("token")
    for raw in (
        {"unknown_option": True},
        {"remote_enabled": "false"},
        {"auth_session_url": "http://127.0.0.1:9999/api/auth/session"},
    ):
        path.write_text(json.dumps(raw))
        with pytest.raises(ValueError):
            Config.load(str(path))


def test_admitted_release_external_io_lock_cannot_be_overridden(tmp_path, monkeypatch):
    import json

    from tracking.config import Config

    monkeypatch.setenv("IKUN_TRACKING_EXTERNAL_IO_DISABLED", "1")
    path = tmp_path / "tracking.json"
    for changes in (
        {"remote_enabled": True},
        {"dedicated_account": True},
        {"token_file": "forbidden-provider-file"},
    ):
        path.write_text(json.dumps({"db_path": str(tmp_path / "tracking/tracking.db"), **changes}))
        with __import__("pytest").raises(ValueError, match="external collection disabled"):
            Config.load(str(path))

@pytest.mark.parametrize('handles',[['UPPER'],['bad-handle'],['same','same'],'not-a-list',[123]])
def test_invalid_adoptable_handles_rejected(tmp_path,handles):
    p=tmp_path/'config.json';p.write_text(json.dumps({'adoptable_handles':handles}))
    with pytest.raises(ValueError,match='adoptable_handles'):Config.load(str(p))

def test_adoption_snapshot_rejects_shared_overlap(tmp_path):
    p=tmp_path/'config.json';p.write_text(json.dumps({'adoptable_handles':['tampad_'],'shared_watch_ids':{'tampad_':'777'}}))
    with pytest.raises(ValueError,match='shared watches cannot be adopted'):Config.load(str(p))
