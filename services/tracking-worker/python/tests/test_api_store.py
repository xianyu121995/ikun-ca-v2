import json
import os
import sqlite3
import time

import pytest
from conftest import add
from fastapi.testclient import TestClient

from tracking.api import Actor, create_app
from tracking.config import Config
from tracking.store import Store

ADMIN = {"Authorization": "Bearer test-admin-credential-xxxxxxxxxxxxxxxxx"}
READER = {"Authorization": "Bearer test-reader-credential-xxxxxxxxxxxxxxxx"}
NEW = {
    "project_id": "prj_550e8400-e29b-41d4-a716-446655440001",
    "name": "项目一",
    "handle": "@Project1",
    "confirmed": True,
}


@pytest.fixture
def client(cfg, store):
    with TestClient(create_app(cfg, store)) as client:
        yield client


def test_auth_and_superadmin_confirmation(client, store):
    assert client.get("/api/tracking/projects").status_code == 401
    assert client.get("/api/tracking/projects", headers={"X-Role": "superadmin"}).status_code == 401
    headers = {**READER, "Idempotency-Key": "create-key"}
    assert client.post("/api/tracking/projects", json=NEW, headers=headers).status_code == 403
    headers = {**ADMIN, "Idempotency-Key": "create-key"}
    assert (
        client.post("/api/tracking/projects", json={**NEW, "confirmed": False}, headers=headers).status_code
        == 422
    )
    response = client.post("/api/tracking/projects", json=NEW, headers=headers)
    assert response.status_code == 202 and response.json()["status"] == "pending"
    assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["confirmed_by"] == "superadmin"
    assert client.post("/api/tracking/projects", json=NEW, headers=headers).status_code == 202
    assert (
        client.post("/api/tracking/projects", json={**NEW, "name": "其他"}, headers=headers).status_code
        == 409
    )
    assert client.get("/api/tracking/projects", headers=READER).json()["items"][0]["handle"] == "project1"


def test_api_full_commands_and_expected_revision(client, store):
    add(store)
    assert (
        client.patch(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001",
            json={"expected_revision": 1, "name": "新名称"},
            headers={**ADMIN, "Idempotency-Key": "edit-key"},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001/stop",
            json={"expected_revision": 1},
            headers={**ADMIN, "Idempotency-Key": "stop-key"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001/stop",
            json={"expected_revision": 2},
            headers={**ADMIN, "Idempotency-Key": "stop-key"},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001/resume",
            json={"expected_revision": 3},
            headers={**ADMIN, "Idempotency-Key": "resume-key"},
        ).status_code
        == 202
    )
    response = client.request(
        "DELETE",
        "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001",
        json={"expected_revision": 4},
        headers={**ADMIN, "Idempotency-Key": "remove-key"},
    )
    assert response.status_code == 202 and response.json()["desired"] == "removed"
    assert response.json()["status"] != "removed"
    assert (
        client.get(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001", headers=READER
        ).status_code
        == 200
    )
    assert client.get("/api/tracking/projects/missing", headers=ADMIN).status_code == 404


def test_status_remote_and_heartbeat_must_both_be_fresh(client, store):
    row = add(store)
    store.observe(row, remote_state="active", status="running", claim="owned", observed_at=time.time())
    assert (
        client.get("/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001", headers=READER).json()[
            "status"
        ]
        == "recovering"
    )
    store.runtime(heartbeat=time.time(), connection="connected", pong_at=time.time())
    assert client.get("/api/tracking/status", headers=READER).json()["monitoring"] == 1
    store.observe(row, observed_at=time.time() - 100)
    assert (
        client.get("/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001", headers=READER).json()[
            "remote_state"
        ]
        == "unknown"
    )
    assert client.get("/api/tracking/status", headers=READER).json()["monitoring"] == 0
    store.runtime(heartbeat=time.time() - 100)
    assert client.get("/api/tracking/status", headers=READER).json()["engine"]["alive"] is False


def test_latest_and_cursor_no_duplicates(client, store):
    row = add(store)
    for i in range(3):
        store.insert_tweet(row, {"tweet_id": str(i + 1), "text": "测试", "created_at": time.time()}, "wss")
    first = client.get("/api/tracking/activities?limit=2", headers=READER).json()
    assert len(first["items"]) == 2 and first["next_cursor"] == 2
    second = client.get("/api/tracking/activities?after=2", headers=READER).json()
    assert len(second["items"]) == 1
    latest = client.get(
        "/api/tracking/latest?limit=1&project_id=prj_550e8400-e29b-41d4-a716-446655440001", headers=READER
    ).json()
    assert latest["items"][0]["tweet_id"] == "3"
    assert latest["items"][0]["url"] == "https://x.com/project1/status/3"
    assert (
        client.get(
            "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001/activities", headers=READER
        ).status_code
        == 200
    )


def test_cookie_login_csrf_logout_and_rate_limit(client):
    response = client.post("/api/tracking/session", json={"token": ADMIN["Authorization"][7:]})
    assert response.status_code == 200
    assert (
        "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    )
    assert client.get("/api/tracking/me").json()["role"] == "superadmin"
    assert (
        client.post("/api/tracking/projects", json=NEW, headers={"Idempotency-Key": "create-key"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/tracking/projects",
            json=NEW,
            headers={
                "Idempotency-Key": "create-key",
                "X-Tracking-CSRF": "1",
                "Origin": "https://attacker.invalid",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/tracking/projects",
            json=NEW,
            headers={"Idempotency-Key": "create-key", "X-Tracking-CSRF": "1"},
        ).status_code
        == 202
    )
    assert client.delete("/api/tracking/session", headers={"X-Tracking-CSRF": "1"}).status_code == 200
    assert client.get("/api/tracking/me").status_code == 401
    for _ in range(9):
        assert client.post("/api/tracking/session", json={"token": "bad"}).status_code == 401
    assert client.post("/api/tracking/session", json={"token": "bad"}).status_code == 429


def test_trusted_auth_adapter_and_page_security(cfg, store):
    with TestClient(
        create_app(cfg, store, authorize=lambda request: Actor("verified-root", "superadmin"))
    ) as c:
        assert (
            c.post("/api/tracking/projects", json=NEW, headers={"Idempotency-Key": "create-key"}).status_code
            == 202
        )
        assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["confirmed_by"] == "verified-root"
        response = c.get("/tracking")
        assert response.status_code == 200 and "项目监控" in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert "test-admin" not in response.text
        assert c.get("/tracking-assets/app.js").status_code == 200


def test_refuse_symlink_hardlink_foreign_and_protected_db(tmp_path):
    protected = tmp_path / "hunter.db"
    with sqlite3.connect(protected) as db:
        db.execute("CREATE TABLE existing(data TEXT)")
    before = protected.read_bytes()
    with pytest.raises(ValueError):
        Store(protected)
    target = tmp_path / "tracking.db"
    target.symlink_to(protected)
    with pytest.raises(ValueError):
        Store(target)
    target.unlink()
    os.link(protected, target)
    with pytest.raises(ValueError):
        Store(target)
    target.unlink()
    target.write_bytes(before)
    with pytest.raises(ValueError, match="foreign database"):
        Store(target)
    assert protected.read_bytes() == before


def test_config_local_paths_permissions_and_unknown_options(tmp_path, monkeypatch):
    secret = tmp_path / "secret"
    secret.write_text("secret")
    secret.chmod(0o600)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token_file": "secret", "db_path": "data/tracking.db"}))
    cfg = Config.load(str(path))
    assert cfg.secret("token") == "secret"
    assert cfg.db_path == tmp_path / "data/tracking.db"
    secret.chmod(0o644)
    with pytest.raises(ValueError):
        cfg.secret("token")
    path.write_text(json.dumps({"remote_enabled": "false"}))
    with pytest.raises(ValueError):
        Config.load(str(path))
    path.write_text(json.dumps({"unknown_secret": "bad"}))
    with pytest.raises(ValueError):
        Config.load(str(path))
