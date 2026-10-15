import concurrent.futures
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from projects_service.api import Settings, create_app
from projects_service.db import APPLICATION_ID, Database, DomainError, create_project, digest, import_project
from projects_service.models import ProjectFields, ProjectImport


def test_migrations_repeat_restart_and_permissions(env, create):
    client, db, actors = env
    project = create({'name': '持久化项目'})
    db.migrate()
    db.migrate()
    with db.connect() as con:
        assert con.execute('PRAGMA application_id').fetchone()[0] == APPLICATION_ID
        assert con.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 2
        assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with TestClient(create_app(Settings(db_path=str(db.path), origin='http://testserver'))) as restarted:
        response = restarted.get('/api/home/projects/' + project['id'], headers=actors['user']['headers'])
        assert response.status_code == 200
        assert response.json()['name'] == '持久化项目'
    assert db.path.stat().st_mode & 0o777 == 0o600


def test_full_crud_and_optimistic_lock(env, create):
    client, db, actors = env
    p = create({'rating': 'A', 'description': '真实简介', 'website': 'https://example.org', 'notes': '首轮调研', 'progress': 'researching'})
    assert re.fullmatch(r'prj_[0-9a-f-]{36}', p['id'])
    payload = {'expected_version': 1, 'rating': 'S', 'description': '已验证', 'website': 'https://example.com',
               'notes': '完成研究', 'progress': 'watching', 'token_date': '2099-12-31', 'token_date_status': 'estimated'}
    updated = client.patch('/api/home/projects/' + p['id'], json=payload, headers=actors['superadmin']['headers'])
    assert updated.status_code == 200
    assert updated.json()['version'] == 2
    assert updated.json()['notes'] == '完成研究'
    assert client.patch('/api/home/projects/' + p['id'], json=payload, headers=actors['superadmin']['headers']).status_code == 409
    assert client.delete('/api/home/projects/' + p['id'] + '?expected_version=1', headers=actors['superadmin']['headers']).status_code == 409
    assert client.delete('/api/home/projects/' + p['id'] + '?expected_version=2', headers=actors['superadmin']['headers']).status_code == 204
    assert client.get('/api/home/projects/' + p['id'], headers=actors['user']['headers']).status_code == 410
    assert client.get('/api/home/projects', headers=actors['user']['headers']).json()['total'] == 0
    with db.connect() as con:
        assert [r['action'] for r in con.execute('SELECT action FROM audit_log ORDER BY id')] == ['create','update','delete']


@pytest.mark.parametrize('role,create_status,edit_status,delete_status', [
    ('user',403,403,403), ('superadmin',201,200,204), ('importer',403,403,403)
])
def test_server_role_matrix(env, create, role, create_status, edit_status, delete_status):
    client, _, actors = env
    p = create()
    headers = actors[role]['headers']
    assert client.get('/api/home/projects', headers=headers).status_code == (403 if role == 'importer' else 200)
    assert client.post('/api/home/projects', json={'name': '另一个'}, headers={**headers, 'Idempotency-Key':'role-create-test'}).status_code == create_status
    assert client.patch('/api/home/projects/' + p['id'], json={'expected_version': 1, 'name': '修改'}, headers=headers).status_code == edit_status
    version = 2 if edit_status == 200 else 1
    assert client.delete('/api/home/projects/' + p['id'] + f'?expected_version={version}', headers=headers).status_code == delete_status


@pytest.mark.parametrize('path', ['/api/home/projects','/api/home/tracking','/api/home/important-times','/api/home/session'])
def test_no_auth_or_forged_roles(env, path):
    client, _, _ = env
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'X-Role':'superadmin','X-User-Id':'1','Authorization':'Bearer forged'}).status_code == 401


def test_manual_idempotency_and_conflicting_replay(env):
    client, _, actors = env
    headers = {**actors['superadmin']['headers'], 'Idempotency-Key':'stable-create-key'}
    first = client.post('/api/home/projects', json={'name':'一次创建'}, headers=headers)
    again = client.post('/api/home/projects', json={'name':'一次创建'}, headers=headers)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()['project']['id'] == again.json()['project']['id']
    assert client.post('/api/home/projects', json={'name':'更改请求'}, headers=headers).status_code == 409
    assert client.post('/api/home/projects', json={'name':'无幂等键'}, headers=actors['superadmin']['headers']).status_code == 422


def test_import_dedup_sources_and_no_overwrite(env, create):
    client, db, actors = env
    p = create({'website':'https://www.example.org/?utm_source=test', 'notes':'用户备注'})
    payload = {'source':'hunter','external_id':'source-01','explicit_add':True,'project':{'name':'来源名','website':'http://example.org','notes':'不应覆盖'}}
    one = client.post('/api/home/imports', json=payload, headers=actors['importer']['headers'])
    two = client.post('/api/home/imports', json={**payload,'project':{'name':'再次导入'}}, headers=actors['importer']['headers'])
    assert one.status_code == two.status_code == 200
    assert one.json()['project']['id'] == two.json()['project']['id'] == p['id']
    assert two.json()['project']['notes'] == '用户备注'
    payload.update(source='tracking', external_id='track-1')
    three = client.post('/api/home/imports', json=payload, headers=actors['tracking']['headers'])
    assert three.json()['project']['id'] == p['id']
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM project_sources').fetchone()[0] == 2
    client.delete('/api/home/projects/'+p['id']+'?expected_version=1', headers=actors['superadmin']['headers'])
    assert client.post('/api/home/imports', json=payload, headers=actors['tracking']['headers']).status_code == 410
    assert client.post('/api/home/projects', json={'name':'不能自动恢复','website':'https://example.org'}, headers={**actors['superadmin']['headers'],'Idempotency-Key':'deleted-test-key'}).status_code == 410


@pytest.mark.parametrize('role', ['user','superadmin'])
def test_human_roles_cannot_import(env, role):
    client, _, actors = env
    payload = {'source':'hunter','external_id':'x','explicit_add':True,'project':{'name':'测试'}}
    assert client.post('/api/home/imports', json=payload, headers=actors[role]['headers']).status_code == 403


@pytest.mark.parametrize('explicit', [False, None, 'true', 1])
def test_import_requires_explicit_boolean(env, explicit):
    client, _, actors = env
    assert client.post('/api/home/imports', json={'source':'hunter','external_id':'x','explicit_add':explicit,'project':{'name':'测试'}}, headers=actors['importer']['headers']).status_code == 422


def test_import_source_binding_and_secret_fields_rejected(env):
    client, _, actors = env
    payload = {'source':'tracking','external_id':'x','explicit_add':True,'project':{'name':'测试'}}
    assert client.post('/api/home/imports', json=payload, headers=actors['importer']['headers']).status_code == 403
    payload['source'] = 'hunter'
    payload['project']['hunter_identity'] = 'must-not-store'
    rejected = client.post('/api/home/imports', json=payload, headers=actors['importer']['headers'])
    assert rejected.status_code == 422 and 'must-not-store' not in rejected.text


def test_atomic_concurrent_imports_and_creates(env):
    _, db, actors = env
    payload = ProjectImport(source='hunter',external_id='race',explicit_add=True,project=ProjectFields(name='并发'))
    def ingest(_):
        with db.transaction() as con:
            return import_project(con, payload, actors['importer']['id'])[0]['id']
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(ingest, range(20)))
    assert len(set(ids)) == 1
    def manual(_):
        with db.transaction() as con:
            return create_project(con, ProjectFields(name='幂等并发'), actors['superadmin']['id'], 'parallel-key')[0]['id']
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(manual, range(20)))
    assert len(set(ids)) == 1


def test_search_all_fields_filter_and_paging(env, create):
    client, _, actors = env
    create({'name':'ALPHA','rating':'S','description':'Rollup 链','progress':'watching'})
    create({'name':'Beta','rating':'A','notes':'独特备注 100%_done','website':'https://beta.example'})
    create({'name':'Gamma','rating':'B','token_date':'2099-12-30','token_date_status':'confirmed'})
    headers = actors['user']['headers']
    for query in ('alpha','链','独特备注','beta.example','100%_done'):
        assert client.get('/api/home/projects', params={'q':query}, headers=headers).json()['total'] == 1
    assert client.get('/api/home/projects', params={'q':"' OR 1=1--"}, headers=headers).json()['total'] == 0
    filtered = client.get('/api/home/projects?rating=S&progress=watching', headers=headers).json()
    assert filtered['total'] == 1 and filtered['items'][0]['name'] == 'ALPHA'
    first = client.get('/api/home/projects?sort=rating&limit=2', headers=headers).json()
    second = client.get('/api/home/projects?sort=rating&limit=2&offset=2', headers=headers).json()
    assert [p['rating'] for p in first['items'] + second['items']] == ['S','A','B']
    assert first['total'] == second['total'] == 3
    for sort in ('updated','discovered_desc','discovered_asc','rating','token_date','name'):
        result = client.get('/api/home/projects', params={'sort':sort}, headers=headers)
        assert result.status_code == 200
        if sort == 'name': assert [p['name'] for p in result.json()['items']] == ['ALPHA','Beta','Gamma']
        if sort == 'token_date': assert result.json()['items'][0]['name'] == 'Gamma'


@pytest.mark.parametrize('params', [{'limit':0},{'limit':101},{'offset':-1},{'rating':'C'},{'progress':'anything'},{'sort':'name;DROP TABLE projects'},{'q':'x'*201}])
def test_query_validation(env, params):
    client, _, actors = env
    assert client.get('/api/home/projects', params=params, headers=actors['user']['headers']).status_code == 422


@pytest.mark.parametrize('data', [
    {'name':''},{'name':'   '},{'name':'x'*121},{'rating':'C'},{'progress':'bad'},
    {'website':'javascript:alert(1)'},{'website':'https://user:password@example.com'},
    {'website':'https://example.com:invalid'}, {'website':'https://ex ample.com'},
    {'notes':None},{'description':'x'*10001}, {'id':'override'},
    {'token_date':'2099-12-30'}, {'token_date_status':'confirmed'}, {'token_date':'not-a-date'}
])
def test_project_input_validation(env, data):
    client, _, actors = env
    response = client.post('/api/home/projects', json={'name':'测试',**data}, headers={**actors['superadmin']['headers'],'Idempotency-Key':'validation-key'})
    assert response.status_code == 422, response.text


def test_patch_validation_and_failed_write_rollback(env, create):
    client, db, actors = env
    p = create({'name':'旧名称'})
    headers = actors['superadmin']['headers']
    for data in ({'expected_version':1,'name':None}, {'expected_version':1}, {'expected_version':1,'token_date':'2099-12-30'}, {'expected_version':0,'notes':'test'}):
        assert client.patch('/api/home/projects/'+p['id'], json=data, headers=headers).status_code == 422
    with db.connect() as con:
        assert con.execute('SELECT name,version FROM projects WHERE id=?',(p['id'],)).fetchone()[:] == ('旧名称',1)
        assert con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == 1


def test_duplicate_website_and_missing_ids(env, create):
    client, _, actors = env
    create({'website':'https://example.com/'})
    p = create()
    assert client.patch('/api/home/projects/'+p['id'], json={'expected_version':1,'website':'http://www.example.com'}, headers=actors['superadmin']['headers']).status_code == 409
    assert client.get('/api/home/projects/prj_00000000-0000-4000-8000-000000000000', headers=actors['user']['headers']).status_code == 404
    assert client.get('/api/home/projects/invalid-id', headers=actors['user']['headers']).status_code == 422


def test_important_times_only_active_real_dates(env, create):
    client, _, actors = env
    create({'name':'没有日期'})
    create({'name':'过去','token_date':'2000-01-01','token_date_status':'confirmed'})
    p = create({'name':'即将发币','token_date':'2099-01-01','token_date_status':'estimated'})
    response = client.get('/api/home/important-times', headers=actors['user']['headers']).json()
    assert response['total'] == 1 and response['items'][0]['project_id'] == p['id']
    assert response['items'][0]['date_status'] == 'estimated'
    client.delete('/api/home/projects/'+p['id']+'?expected_version=1', headers=actors['superadmin']['headers'])
    assert client.get('/api/home/important-times', headers=actors['user']['headers']).json()['total'] == 0


def test_cookie_csrf_logout_expiry_and_revocation(env):
    client, db, actors = env
    assert client.post('/api/home/session', json={'token':actors['superadmin']['token']}).status_code == 403
    login = client.post('/api/home/session', json={'token':actors['superadmin']['token']}, headers={'Origin':'http://testserver'})
    assert login.status_code == 200
    assert 'HttpOnly' in login.headers['set-cookie'] and 'SameSite=strict' in login.headers['set-cookie']
    csrf = login.json()['csrf_token']
    body, headers = {'name':'会话测试'}, {'Origin':'http://testserver','X-CSRF-Token':csrf,'Idempotency-Key':'cookie-create-key'}
    assert client.post('/api/home/projects', json=body).status_code == 403
    assert client.post('/api/home/projects', json=body, headers={**headers,'Origin':'http://evil.example'}).status_code == 403
    assert client.post('/api/home/projects', json=body, headers=headers).status_code == 201
    assert client.delete('/api/home/session', headers=headers).status_code == 204
    assert client.get('/api/home/projects').status_code == 401
    login = client.post('/api/home/session', json={'token':actors['superadmin']['token']}, headers={'Origin':'http://testserver'})
    with db.transaction() as con:
        con.execute('UPDATE sessions SET expires_at=?', (int(time.time())-1,))
    assert client.get('/api/home/projects').status_code == 401
    with db.transaction() as con:
        con.execute('UPDATE principals SET disabled=1 WHERE id=?', (actors['superadmin']['id'],))
    assert client.get('/api/home/projects', headers=actors['superadmin']['headers']).status_code == 401


def test_login_invalid_token_not_echoed_and_importer_cannot_login(env):
    client, _, actors = env
    secret = 'bad-secret'
    invalid = client.post('/api/home/session', json={'token':secret}, headers={'Origin':'http://testserver'})
    assert invalid.status_code == 422 and secret not in invalid.text
    assert client.post('/api/home/session', json={'token':'x'*64}, headers={'Origin':'http://testserver'}).status_code == 401
    assert client.post('/api/home/session', json={'token':actors['importer']['token']}, headers={'Origin':'http://testserver'}).status_code == 403


def test_rate_limit_body_bound_host_and_headers(env):
    _, db, actors = env
    settings = Settings(db_path=str(db.path), origin='http://testserver', rate_limit=2, login_limit=1)
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/home/projects', headers=actors['user']['headers']).status_code == 200
        assert client.get('/api/home/projects', headers=actors['user']['headers']).status_code == 200
        limited = client.get('/api/home/projects', headers=actors['user']['headers'])
        assert limited.status_code == 429 and limited.headers['retry-after'] == '60'
        assert client.post('/api/home/session', json={'token':'x'*64}, headers={'Origin':'http://testserver'}).status_code == 401
        assert client.post('/api/home/session', json={'token':'x'*64}, headers={'Origin':'http://testserver'}).status_code == 429
        assert client.post('/api/home/projects', content='x'*50000).status_code == 413
        assert client.get('/healthz', headers={'Host':'evil.example'}).status_code == 400
        page = client.get('/')
        assert page.status_code == 200 and "script-src 'self'" in page.headers['content-security-policy']
        assert page.headers['cache-control'] == 'no-store'
        assert client.get('/assets/unknown').status_code == 422


def test_database_busy_returns_retryable_error(env):
    client, db, actors = env
    with db.transaction():
        response = client.post('/api/home/projects', json={'name':'锁测试'}, headers={**actors['superadmin']['headers'],'Idempotency-Key':'locked-create-key'})
    assert response.status_code == 503 and response.json()['error']['code'] == 'database_busy'


def test_migration_refuses_foreign_db_symlink_hardlink_and_drift(tmp_path):
    path = tmp_path/'projects.db'
    foreign = sqlite3.connect(path)
    foreign.execute('CREATE TABLE protected(value TEXT)')
    foreign.close()
    before = path.read_bytes()
    with pytest.raises(RuntimeError): Database(path).migrate()
    assert path.read_bytes() == before
    with pytest.raises(ValueError): Database(tmp_path/'hunter.db')
    link = tmp_path/'linked'
    link.mkdir()
    (link/'projects.db').symlink_to(path)
    with pytest.raises(ValueError): Database(link/'projects.db')
    (link/'projects.db').unlink()
    os.link(path, link/'projects.db')
    with pytest.raises(ValueError): Database(link/'projects.db')
    (link/'projects.db').unlink()
    path.unlink()
    db = Database(path)
    db.migrate()
    with db.transaction() as con:
        con.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(RuntimeError): db.migrate()


def test_only_projects_db_connections_and_delete_never_touches_other_files(env, create, monkeypatch, tmp_path):
    client, db, actors = env
    # These are opaque sentinel files. The test and service never open any other business DB.
    sentinels = [tmp_path/'hunter.sentinel',tmp_path/'monitor.sentinel']
    for path in sentinels: path.write_bytes(os.urandom(128))
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in sentinels]
    connect, opened = sqlite3.connect, []
    def guarded(path, *args, **kwargs):
        assert str(path).startswith(db.path.as_uri()+'?mode=rw'), str(path)
        opened.append(str(path))
        return connect(path,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',guarded)
    p = create()
    client.get('/api/home/projects',headers=actors['superadmin']['headers'])
    client.delete('/api/home/projects/'+p['id']+'?expected_version=1',headers=actors['superadmin']['headers'])
    assert opened
    assert hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in sentinels]


def test_import_failure_rolls_back_all_rows(env, monkeypatch):
    _, db, actors = env
    from projects_service import db as module
    original = module.audit
    def failure(con, actor, action, project_id, fields, tenant='default'):
        if action == 'import_link': raise RuntimeError('fixture storage failure')
        return original(con,actor,action,project_id,fields,tenant)
    monkeypatch.setattr(module,'audit',failure)
    payload = ProjectImport(source='hunter',external_id='rollback',explicit_add=True,project=ProjectFields(name='回滚'))
    with pytest.raises(RuntimeError):
        with db.transaction() as con: import_project(con,payload,actors['importer']['id'])
    with db.connect() as con:
        for table in ('projects','project_sources','audit_log'):
            assert con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_settings_public_https_required():
    with pytest.raises(ValueError): Settings(origin='http://example.com')
    with pytest.raises(ValueError): Settings(origin='https://example.com')
    assert Settings(origin='https://example.com',secure_cookie=True)
    with pytest.raises(ValueError): Settings(proxy_authority='example.com:8120')
    with pytest.raises(ValueError): Settings(proxy_authority='127.0.0.1:8120/unsafe')


def test_proxy_loopback_host_requires_public_origin_csrf(env):
    _,db,actors=env
    app=create_app(Settings(db_path=str(db.path),origin='http://testserver',proxy_authority='127.0.0.1:8120'))
    with TestClient(app) as client:
        assert client.get('/healthz',headers={'Host':'127.0.0.1:8120'}).status_code==200
        assert client.post('/api/home/session',json={'token':actors['superadmin']['token']},headers={'Host':'127.0.0.1:8120','Origin':'http://127.0.0.1:8120'}).status_code==403
        assert client.post('/api/home/session',json={'token':actors['superadmin']['token']},headers={'Host':'127.0.0.1:8120','Origin':'http://testserver'}).status_code==200


@pytest.mark.parametrize('role',['viewer','editor','admin','importer'])
def test_legacy_user_roles_cannot_be_provisioned(env,role):
    _, db, _ = env
    with pytest.raises(ValueError): db.create_principal(role)
    with pytest.raises(ValueError): db.create_principal('superadmin',source='hunter')


def test_tenant_isolation_is_derived_only_from_server_credentials(env, create):
    client, db, actors = env
    original = create({'name':'租户一项目','website':'https://shared.example','token_date':'2099-01-01','token_date_status':'confirmed'})
    _, token = db.create_principal('superadmin', tenant='tenant-two')
    other = {'Authorization':'Bearer '+token}
    assert client.get('/api/home/projects',headers=other).json()['total']==0
    assert client.get('/api/home/important-times',headers=other).json()['total']==0
    assert client.get('/api/home/projects/'+original['id'],headers=other).status_code==404
    assert client.patch('/api/home/projects/'+original['id'],json={'expected_version':1,'name':'篡改'},headers=other).status_code==404
    assert client.delete('/api/home/projects/'+original['id']+'?expected_version=1',headers=other).status_code==404
    response=client.post('/api/home/projects',json={'name':'租户二项目','website':'https://shared.example'},headers={**other,'Idempotency-Key':'other-tenant-key'})
    assert response.status_code==201
    assert response.json()['project']['id']!=original['id']
    assert client.get('/api/home/projects',headers=actors['user']['headers']).json()['total']==1
    # Body/header tenant impersonation is never accepted.
    assert client.post('/api/home/projects',json={'name':'伪造租户','tenant_id':'default'},headers={**other,'Idempotency-Key':'spoof-tenant-key'}).status_code==422
    assert client.get('/api/home/projects',headers={**other,'X-Tenant-Id':'default'}).json()['items'][0]['name']=='租户二项目'


def test_import_identity_is_scoped_to_tenant(env):
    client, db, actors = env
    _, token = db.create_principal(None,source='hunter',tenant='tenant-two')
    payload={'source':'hunter','external_id':'same-external-id','explicit_add':True,'project':{'name':'来源项目','website':'https://shared.example'}}
    first=client.post('/api/home/imports',json=payload,headers=actors['importer']['headers'])
    second=client.post('/api/home/imports',json=payload,headers={'Authorization':'Bearer '+token})
    assert first.status_code==second.status_code==201
    assert first.json()['project']['id']!=second.json()['project']['id']


def test_error_request_id_and_retryability(env):
    client, _, _ = env
    response=client.get('/api/home/projects',headers={'X-Request-Id':'req_123'})
    assert response.headers['x-request-id']=='req_123'
    assert response.json()['request_id']=='req_123'
    assert response.json()['error']['retryable'] is False


def test_upgrade_from_foundation_keeps_its_identity_tables(tmp_path):
    path=tmp_path/'projects.db'
    with sqlite3.connect(path) as con:
        con.execute(f'PRAGMA application_id={APPLICATION_ID}')
        con.execute('CREATE TABLE _store_identity(singleton INTEGER PRIMARY KEY,store_name TEXT)')
        con.execute("INSERT INTO _store_identity VALUES(1,'projects')")
        con.execute('CREATE TABLE _schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)')
        con.execute("INSERT INTO _schema_migrations VALUES(1,'foundation','2026-10-15')")
    Database(path).migrate()
    with Database(path).connect() as con:
        assert con.execute('SELECT store_name FROM _store_identity').fetchone()[0]=='projects'
        assert con.execute('SELECT COUNT(*) FROM _schema_migrations').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==2


def test_import_can_link_canonical_id_without_overwriting_and_receipt_is_durable(env, create):
    client, db, actors = env
    p=create({'name':'保留的人工项目','notes':'人工内容'})
    other=create({'name':'另一个项目','website':'https://different.example'})
    payload={'source':'hunter','external_id':'link-existing','explicit_add':True,'project_id':p['id'],'project':{'name':'外部名称'}}
    headers=actors['importer']['headers']
    result=client.post('/api/home/imports',json=payload,headers=headers)
    assert result.status_code==200 and result.json()['project']['id']==p['id']
    assert result.json()['project']['notes']=='人工内容'
    changed=client.post('/api/home/imports',json={**payload,'project_id':other['id']},headers=headers)
    assert changed.status_code==409 and changed.json()['error']['code']=='mapping_conflict'
    website_conflict=client.post('/api/home/imports',json={**payload,'external_id':'different-id','project':{'name':'冲突','website':'https://different.example'}},headers=headers)
    assert website_conflict.status_code==409
    query={'source':'hunter','external_id':'link-existing'}
    receipt=client.get('/api/home/import-receipts',params=query,headers=headers)
    assert receipt.status_code==200 and receipt.json()['project_id']==p['id']
    assert receipt.json()['deleted'] is False
    assert client.get('/api/home/import-receipts',params={**query,'source':'tracking'},headers=headers).status_code==403
    assert client.get('/api/home/import-receipts',params={**query,'external_id':'missing'},headers=headers).status_code==404
    client.delete('/api/home/projects/'+p['id']+'?expected_version=1',headers=actors['superadmin']['headers'])
    assert client.get('/api/home/import-receipts',params=query,headers=headers).json()['deleted'] is True
