"""Human identity cases now run against the pinned B1 actual Node entry, not a Python getter."""

from fastapi.testclient import TestClient

from tracking.api import create_app


def test_legacy_auth_sessions_cannot_authorize(cfg, store):
    with TestClient(create_app(cfg, store)) as client:
        for path in ("/api/tracking/me", "/api/tracking/projects", "/api/tracking/session"):
            assert (
                client.get(
                    path, headers={"Cookie": "tracking_session=old", "X-Role": "superadmin"}
                ).status_code
                == 404
            )
    try:
        store.session("token", "superadmin")
    except ValueError as e:
        assert "auth.db" in str(e)
    else:
        raise AssertionError("legacy identity must stay disabled")
