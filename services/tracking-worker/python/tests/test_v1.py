from fastapi.testclient import TestClient
from test_api_store import HEAD, envelope

from tracking.api import create_app
from tracking.commands import accept, query
from tracking.protocol import Command


def test_worker_no_longer_exposes_unguarded_public_crud(cfg, store):
    with TestClient(create_app(cfg, store)) as client:
        assert client.post("/api/v1/tracking/subscriptions", json={}, headers=HEAD).status_code == 404
        assert client.get("/tracking").status_code == 404


def test_lease_restart_marks_inflight_unknown(store):
    import time

    from tracking.commands import executing

    cmd = Command.model_validate(envelope())
    accept(store, cmd, "lease-001")
    executing(store, store.get(cmd.project_id))
    store.lease("first", acquire=True)
    store.runtime(heartbeat=time.time() - 31)
    assert store.lease("second", acquire=True)
    assert not store.lease("first")
    assert query(store, cmd.command_id, "lease-002")["state"] == "unknown"
