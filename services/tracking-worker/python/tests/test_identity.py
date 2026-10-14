from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from tracking.api import create_app
from tracking.identity import SessionVerifier


def test_main_site_auth_is_api_only_and_rechecks_revocation(cfg, store):
    cfg = replace(
        cfg,
        auth_session_url="http://127.0.0.1:8123/api/auth/session",
        auth_origin="http://testserver",
        auth_cookie_name="ikun_dev_session",
    )
    user = {"id": "real-user-id", "role": "superadmin", "must_change_password": False}
    revoked = False

    def verify(request):
        assert request.url.path == "/api/auth/session"
        assert request.headers["host"] == "testserver"
        assert request.headers["cookie"] == "ikun_dev_session=verified-session"
        assert "authorization" not in request.headers
        return (
            httpx.Response(401) if revoked else httpx.Response(200, json={"user": user, "csrf_token": "csrf"})
        )

    verifier = SessionVerifier(cfg, httpx.MockTransport(verify))
    with TestClient(create_app(cfg, store, session_verifier=verifier)) as client:
        assert client.get("/api/tracking/projects").status_code == 401
        client.cookies.set("ikun_dev_session", "verified-session")
        assert client.get("/api/tracking/me").json()["subject"] == "real-user-id"
        body = {
            "project_id": "prj_550e8400-e29b-41d4-a716-446655440001",
            "name": "项目",
            "handle": "project1",
            "confirmed": True,
        }
        headers = {"Idempotency-Key": "create-key", "Origin": "http://testserver", "X-CSRF-Token": "csrf"}
        assert client.post("/api/tracking/projects", json=body, headers=headers).status_code == 202
        assert store.get("prj_550e8400-e29b-41d4-a716-446655440001")["confirmed_by"] == "real-user-id"
        user["role"] = "user"
        assert (
            client.post(
                "/api/tracking/projects/prj_550e8400-e29b-41d4-a716-446655440001/stop",
                json={"expected_revision": 1},
                headers=headers,
            ).status_code
            == 403
        )
        assert client.get("/api/tracking/projects").status_code == 200
        revoked = True
        assert client.get("/api/tracking/projects").status_code == 401
        assert client.post("/api/tracking/session", json={"token": "anything"}).status_code == 403


def test_main_site_auth_unavailable_fails_closed(cfg, store):
    cfg = replace(cfg, auth_session_url="http://127.0.0.1:8123/api/auth/session")
    verifier = SessionVerifier(cfg, httpx.MockTransport(lambda request: httpx.Response(503)))
    with TestClient(create_app(cfg, store, session_verifier=verifier)) as client:
        client.cookies.set(cfg.auth_cookie_name, "session")
        assert client.get("/api/tracking/projects").status_code == 503
