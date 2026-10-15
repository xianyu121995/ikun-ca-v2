import pytest
from fastapi.testclient import TestClient

from projects_service.api import Settings, create_app
from projects_service.db import Database


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / 'projects.db')
    db.migrate()
    actors = {}
    for role in ('user','superadmin','importer'):
        actor_id, token = db.create_principal(None if role=='importer' else role, 'hunter' if role == 'importer' else None)
        actors[role] = {'id': actor_id, 'token': token, 'headers': {'Authorization': 'Bearer ' + token}}
    actors['tracking'] = {}
    actor_id, token = db.create_principal(None, 'tracking')
    actors['tracking'] = {'id': actor_id, 'token': token, 'headers': {'Authorization': 'Bearer ' + token}}
    app = create_app(Settings(db_path=str(db.path), origin='http://testserver', rate_limit=10000))
    with TestClient(app) as client:
        yield client, db, actors


@pytest.fixture
def create(env):
    client, _, actors = env
    counter = 0

    def new(data=None):
        nonlocal counter
        counter += 1
        response = client.post('/api/home/projects', json={'name': '测试项目', **(data or {})},
                               headers={**actors['superadmin']['headers'], 'Idempotency-Key': f'test-key-{counter:05d}'})
        assert response.status_code == 201, response.text
        return response.json()['project']
    return new
