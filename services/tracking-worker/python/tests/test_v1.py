from uuid import uuid4

from fastapi.testclient import TestClient

from tracking.api import create_app

ADMIN = {"Authorization": "Bearer test-admin-credential-xxxxxxxxxxxxxxxxx"}


def test_v1_envelope_id_etag_idempotency_and_cursor(cfg, store):
    with TestClient(create_app(cfg, store)) as client:
        path = "/api/v1/tracking/subscriptions"
        project_id = "prj_" + str(uuid4())
        body = {"project_id": project_id, "name": "项目", "handle": "project1", "confirmed": True}
        headers = {**ADMIN, "Idempotency-Key": str(uuid4()), "X-Request-ID": "request-123"}
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201
        assert response.headers["etag"] == '"rev-1"'
        assert response.headers["x-request-id"] == response.json()["request_id"] == "request-123"
        assert response.json()["data"]["created_at"].endswith("Z")
        assert client.post(path, json=body, headers=headers).status_code == 201
        assert (
            client.post(path, json={**body, "name": "changed"}, headers=headers).json()["error"]["code"]
            == "IDEMPOTENCY_CONFLICT"
        )
        response = client.patch(
            path + "/" + project_id, json={"name": "编辑"}, headers={**ADMIN, "Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 428
        response = client.patch(
            path + "/" + project_id,
            json={"name": "编辑"},
            headers={**ADMIN, "Idempotency-Key": str(uuid4()), "If-Match": '"rev-1"'},
        )
        assert response.status_code == 200 and response.headers["etag"] == '"rev-2"'
        response = client.post(
            path + "/" + project_id + "/stop",
            headers={**ADMIN, "Idempotency-Key": str(uuid4()), "If-Match": '"rev-1"'},
        )
        assert response.status_code == 409 and response.json()["error"]["code"] == "VERSION_CONFLICT"
        assert client.get(path + "?limit=101", headers=ADMIN).status_code == 422
        assert client.get(path + "?cursor=bad", headers=ADMIN).status_code == 422
        assert client.get(path).json()["error"]["code"] == "UNAUTHENTICATED"
        assert (
            client.post(
                path,
                json={**body, "project_id": "not-a-project-id"},
                headers={**ADMIN, "Idempotency-Key": str(uuid4())},
            ).status_code
            == 422
        )
        response = client.get(path, headers=ADMIN).json()
        assert response["data"]["items"][0]["project_id"] == project_id


def test_lease_expiry_and_fencing(store):
    import time

    assert store.lease("first", acquire=True)
    assert not store.lease("second", acquire=True)
    store.runtime(heartbeat=time.time() - 31)
    assert store.lease("second", acquire=True)
    assert not store.lease("first")
    assert not store.lease("first", release=True)
    assert store.runtime()["worker_id"] == "second"
