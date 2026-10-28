"""B2 isolated database/IPC evidence. No other store or running service is used."""
import concurrent.futures
import copy
import json
import os
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from projects_service.db import Database, DomainError, insert_project
from projects_service.ipc import IpcConfig, create_ipc_app
from projects_service.migration import FOUNDATION_SQL, FormalDatabase, statements
from projects_service.models import ProjectFields
from projects_service.service import Service
from projects_service.transport import Fields, Rpc

ADMIN={'user_id':'admin_1','tenant_id':'ikun-main','role':'superadmin'}
USER={**ADMIN,'user_id':'user_1','role':'user'}
FIELDS=dict(name='真实项目',rating='A',description='简介',website_url=None,notes='研究备注',category=None,
            progress_stage='researching',progress_percent=None,token_date=None,token_date_status='unconfirmed')
def uid(prefix=''):return prefix+str(uuid.uuid4())

@pytest.fixture
def domain(tmp_path):
    db=FormalDatabase(tmp_path/'projects/projects.db');db.migrate()
    return Service(db)

def call(service,operation,*,principal=ADMIN,**args):
    return service.execute(Rpc(operation=operation,principal=principal,request_id=uid(),**args))

def create(service,**fields):
    return call(service,'create',idempotency_key=uid(),body={**FIELDS,**fields})[1]

def event(**fields):
    return dict(schema_version=1,event_id=uid('evt_'),source='hunter',event_type='hunter.monitoring_requested',
                occurred_at=None,received_at='2026-10-15T00:00:00Z',tenant_id='ikun-main',project_id=None,correlation_id=uid(),
                payload=dict(command_id=uid('cmd_'),discovery_id='discovery-1',source_entity_key='hunter-1',confirmed=True,
                             actor=ADMIN,project={**FIELDS,**fields},x_user_id='123456',x_handle='test_user'))

def test_formal_migration_repeat_and_no_request_ddl(domain):
    db=domain.db;db.inspect();db.migrate();db.inspect()
    with db.connect() as con:
        assert [r[0] for r in con.execute('SELECT version FROM _schema_migrations ORDER BY version')]==[1,2]
        assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        before=con.execute('PRAGMA schema_version').fetchone()[0]
    create(domain);call(domain,'list')
    with db.connect() as con:assert con.execute('PRAGMA schema_version').fetchone()[0]==before
    assert db.path.stat().st_mode & 0o777==0o600

@pytest.mark.parametrize('optional_checksum',[False,True])
def test_foundation_old_ledger_supported(tmp_path,optional_checksum):
    db=FormalDatabase(tmp_path/'projects/projects.db');db.path.parent.mkdir(mode=0o700)
    with sqlite3.connect(db.path) as con:
        statements(con,FOUNDATION_SQL)
        if optional_checksum:con.execute('ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT NOT NULL DEFAULT "old"')
        con.execute('INSERT INTO _schema_migrations(version,name,applied_at) VALUES(1,"foundation","old")')
        con.execute('INSERT INTO _store_identity VALUES(1,"projects")')
        # Use the exact store marker, independent of SQLite decimal rendering.
        from projects_service.db import APPLICATION_ID
        con.execute(f'PRAGMA application_id={APPLICATION_ID}')
    os.chmod(db.path,0o600);db.migrate();db.inspect()

def test_legacy_migration_retains_ids_aliases_and_historical_auth(tmp_path):
    legacy=Database(tmp_path/'projects/projects.db');legacy.migrate()
    with legacy.transaction() as con:p=insert_project(con,ProjectFields(name='旧项目'), 'legacy-admin')
    formal=FormalDatabase(legacy.path);formal.migrate();formal.inspect()
    row=call(Service(formal),'get',target=p['id'])[1]
    assert row['project_id']==p['id'] and row['home_membership']=='active'
    with formal.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM legacy_projects_v1').fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='principals'").fetchone()[0]==0

@pytest.mark.parametrize('mutation',[
    "UPDATE _migration_checksums SET sha256='bad' WHERE version=2",
    "INSERT INTO _schema_migrations VALUES(3,'future','now')",
    "UPDATE _store_identity SET store_name='tracking'",
    "PRAGMA user_version=3",
])
def test_fail_closed_metadata(domain,mutation):
    with domain.db.connect() as con:con.execute(mutation);con.commit()
    with pytest.raises(RuntimeError):domain.db.inspect()
    with pytest.raises(RuntimeError):domain.db.migrate()

def test_migration_atomic_rollback(tmp_path):
    db=FormalDatabase(tmp_path/'projects/projects.db')
    with pytest.raises(RuntimeError,match='INJECTED'):db.migrate(fail_before_commit=True)
    with sqlite3.connect(db.path) as con:assert not con.execute("SELECT name FROM sqlite_master WHERE name='projects'").fetchall()
    db.migrate();db.inspect()

@pytest.mark.parametrize('invalid',['auth.db','tracking.db','hunter.db','projects.db'])
def test_path_boundary(tmp_path,invalid):
    with pytest.raises(ValueError):FormalDatabase(tmp_path/invalid)

def test_symlink_and_hardlink_rejected(tmp_path):
    other=tmp_path/'other';other.write_text('sentinel')
    parent=tmp_path/'projects';parent.mkdir(mode=0o700);path=parent/'projects.db'
    path.symlink_to(other)
    with pytest.raises(ValueError):FormalDatabase(path)
    path.unlink();os.link(other,path)
    with pytest.raises(ValueError):FormalDatabase(path)
    assert other.read_text()=='sentinel'

def test_role_and_scope_enforced(domain):
    assert call(domain,'list',principal=USER)[0]==200
    for actor,expected in [(None,401),(USER,403)]:
        with pytest.raises(DomainError) as exc:call(domain,'create',principal=actor,body=FIELDS,idempotency_key=uid())
        assert exc.value.status==expected
    with pytest.raises(ValidationError):Rpc(operation='list',request_id=uid(),principal={**USER,'tenant_id':'other'})
    with pytest.raises(ValidationError):Rpc(operation='list',request_id=uid(),principal={**USER,'role':'admin'})

def test_crud_revision_membership_identity_independent(domain):
    p=create(domain,rating='C',progress_percent=32.5)
    assert p['rating']=='C' and p['progress_percent']==32.5 and p['discovered_at'] is None
    q=call(domain,'patch',target=p['project_id'],body={'rating':'S','notes':'更新'},if_match='"rev-1"',idempotency_key=uid())[1]
    assert q['revision']==2
    with pytest.raises(DomainError,match='项目已变更'):call(domain,'delete',target=p['project_id'],if_match='"rev-1"',idempotency_key=uid())
    removed=call(domain,'delete',target=p['project_id'],if_match='"rev-2"',idempotency_key=uid())[1]
    assert removed['home_membership']=='removed' and removed['progress_stage']=='researching'
    restored=call(domain,'membership',target=p['project_id'],body={'action':'add'},if_match='"rev-3"',idempotency_key=uid())[1]
    assert restored['project_id']==p['project_id'] and restored['progress_percent']==32.5
    with domain.db.connect() as con:assert con.execute('SELECT COUNT(*) FROM tracking_outbox').fetchone()[0]==1

def test_receipt_concurrent_replay_and_conflict(domain):
    key=uid()
    def write():return call(domain,'create',body=FIELDS,idempotency_key=key)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:write(),range(8)))
    assert len({r[1]['project_id'] for r in results})==1
    assert all(r[0]==201 for r in results)
    with pytest.raises(DomainError) as exc:call(domain,'create',body={**FIELDS,'name':'冲突'},idempotency_key=key)
    assert exc.value.code=='IDEMPOTENCY_CONFLICT'
    query={'method':'POST','path':'/api/v1/projects','contract':'phase2-v1.0.0'}
    receipt=call(domain,'reconcile',target=key,query=query)[1]
    assert receipt['result']['project_id']==results[0][1]['project_id']
    with pytest.raises(DomainError):call(domain,'reconcile',principal=USER,target=key,query=query)
    with domain.db.connect() as con:assert con.execute('SELECT expires_at-strftime("%s",created_at) FROM operation_receipts').fetchone()[0]>=604799

@pytest.mark.parametrize('change',[{'website_url':''},{'website_url':'javascript:alert(1)'},{'rating':'Z'},{'progress_percent':True},{'progress_percent':101},{'token_date':'2026-01-01'},{'notes':'x'*4001},{'extra':'no'}])
def test_strict_fields(change):
    with pytest.raises(ValidationError):Fields.model_validate({**FIELDS,**change})

@pytest.mark.parametrize('query',[{'q':1},{'limit':True},{'limit':0},{'sort':'DROP TABLE'},{'home_membership':'all'},{'discovered_on':'2026-02-30'},{'tenant_id':'other'}])
def test_invalid_queries(domain,query):
    with pytest.raises(DomainError):call(domain,'list',query=query)

@pytest.mark.parametrize('sort',['updated','name','rating','discovered','progress'])
@pytest.mark.parametrize('direction',['asc','desc'])
def test_cursor_all_rows_no_duplicates_and_query_binding(domain,sort,direction):
    ids={create(domain,name='same' if i%2 else f'project{i}',rating=['S','A',None][i%3],progress_percent=None if i%2 else 30)['project_id'] for i in range(13)}
    query={'sort':sort,'direction':direction,'limit':3};seen=[];cursor=None
    while True:
        result=call(domain,'list',query={**query,**({'cursor':cursor} if cursor else {})})[1]
        seen.extend(p['project_id'] for p in result['items']);cursor=result['next_cursor']
        if not cursor:break
        with pytest.raises(DomainError):call(domain,'list',query={**query,'q':'changed','cursor':cursor})
    assert len(seen)==13 and set(seen)==ids

def test_search_escaped_and_shanghai_date(domain):
    a=create(domain,name='100%_项目',notes='唯一词');create(domain,name='ordinary')
    with domain.db.transaction() as con:con.execute('UPDATE projects SET discovered_at=? WHERE id=?',('2026-10-14T16:00:00Z',a['project_id']))
    assert len(call(domain,'list',query={'q':'%_'})[1]['items'])==1
    assert len(call(domain,'list',query={'discovered_on':'2026-10-15'})[1]['items'])==1
    assert not call(domain,'list',query={'discovered_on':'2026-10-14'})[1]['items']

def test_event_atomic_dedup_removed_reimport_no_manual_overwrite(domain):
    e=event();r=call(domain,'ingest',principal=None,source='hunter',body=e)[1]
    repeat=call(domain,'ingest',principal=None,source='hunter',body=e)[1]
    assert repeat['duplicate'] and repeat['receipt_id']==r['receipt_id']
    p=call(domain,'get',target=r['project_id'])[1];assert p['home_membership']=='hidden'
    p=call(domain,'patch',target=p['project_id'],body={'notes':'人工备注'},if_match='"rev-1"',idempotency_key=uid())[1]
    call(domain,'delete',target=p['project_id'],if_match=f'"rev-{p["revision"]}"',idempotency_key=uid())
    other=copy.deepcopy(e);other['event_id']=uid('evt_')
    assert call(domain,'ingest',principal=None,source='hunter',body=other)[1]['project_id']==p['project_id']
    p=call(domain,'get',target=p['project_id'])[1]
    assert p['home_membership']=='removed' and p['notes']=='人工备注'
    conflict=copy.deepcopy(e);conflict['payload']['project']['name']='conflict'
    with pytest.raises(DomainError):call(domain,'ingest',principal=None,source='hunter',body=conflict)
    with domain.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM tracking_outbox').fetchone()[0]==2
    with pytest.raises(DomainError):call(domain,'ingest',principal=None,source='tracking',body=e)

def test_outbox_unknown_reconciles_before_repost(domain):
    e=event();r=call(domain,'ingest',principal=None,source='hunter',body=e)[1];cmd=r['command_id']
    claim=lambda:call(domain,'outbox_claim',principal=None,source='tracking',target=cmd)[1]['item']
    first=claim();assert first['action']=='send'
    call(domain,'outbox_result',principal=None,source='tracking',target=cmd,body={'lease_token':first['lease_token'],'outcome':'unknown'})
    second=claim();assert second['action']=='reconcile'
    call(domain,'outbox_result',principal=None,source='tracking',target=cmd,body={'lease_token':second['lease_token'],'outcome':'not_found'})
    third=claim();assert third['action']=='send'
    result=dict(command_id=cmd,state='succeeded',project_id=r['project_id'],subscription_id=uid('sub_'),revision=1,updated_at='2026-10-15T00:00:00Z',error_code=None,request_id=uid())
    call(domain,'outbox_result',principal=None,source='tracking',target=cmd,body={'lease_token':third['lease_token'],'outcome':'received','result':result})
    assert claim() is None
    assert call(domain,'command',target=cmd)[1]['subscription_id']==result['subscription_id']

def test_cleanup_outbox_id_is_uuid4_shaped_and_idempotent(domain):
    p=create(domain);key=uid()
    call(domain,'membership',target=p['project_id'],body={'action':'remove'},if_match='"rev-1"',idempotency_key=key)
    with domain.db.connect() as con:
        rows=con.execute("SELECT command_id,command_json FROM tracking_outbox WHERE project_id=?",(p['project_id'],)).fetchall()
    assert len(rows)==1
    cid=rows[0]['command_id']
    import re
    assert re.fullmatch(r'cmd_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',cid)
    body=json.loads(rows[0]['command_json'])
    assert body['operation']=='tracking.remove' and body['command_id']==cid
    # Same idempotency key + same body/if_match replays the receipt; still one cleanup row.
    call(domain,'membership',target=p['project_id'],body={'action':'remove'},if_match='"rev-1"',idempotency_key=key)
    with domain.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM tracking_outbox WHERE project_id=?',(p['project_id'],)).fetchone()[0]==1
        assert con.execute('SELECT command_id FROM tracking_outbox WHERE project_id=?',(p['project_id'],)).fetchone()[0]==cid
    # A distinct idempotency key for another remove of the same project yields a distinct deterministic cleanup id.
    other=uid()
    call(domain,'membership',target=p['project_id'],body={'action':'add'},if_match='"rev-2"',idempotency_key=uid())
    call(domain,'membership',target=p['project_id'],body={'action':'remove'},if_match='"rev-3"',idempotency_key=other)
    with domain.db.connect() as con:
        ids=sorted(r[0] for r in con.execute('SELECT command_id FROM tracking_outbox WHERE project_id=?',(p['project_id'],)))
    assert len(ids)==2 and cid in ids and ids[0]!=ids[1]
    import re
    assert all(re.fullmatch(r'cmd_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',i) for i in ids)

def test_legacy_uuid5_cleanup_command_id_accepted_for_outbox_finish(domain):
    # Existing production rows used uuid5; projects must still accept them so relay can finish.
    p=create(domain)
    legacy='cmd_'+str(uuid.uuid5(uuid.NAMESPACE_URL,'tracking-cleanup:legacy-test:'+p['project_id']))
    assert legacy.split('-')[2][0]=='5'
    command={'schema_version':1,'command_id':legacy,'tenant_id':'ikun-main','actor':ADMIN,
             'operation':'tracking.remove','project_id':p['project_id'],'subscription_id':None,
             'expected_revision':None,'payload':{},'issued_at':'2026-10-15T00:00:00Z'}
    body=json.dumps(command,separators=(',',':'),sort_keys=True)
    with domain.db.transaction() as con:
        con.execute('INSERT INTO tracking_outbox(command_id,tenant_id,project_id,command_json,command_hash,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                    (legacy,'ikun-main',p['project_id'],body,uuid.uuid4().hex,'pending','2026-10-15T00:00:00Z','2026-10-15T00:00:00Z'))
    item=call(domain,'outbox_claim',principal=None,source='tracking',target=legacy)[1]['item']
    assert item and item['command']['command_id']==legacy and item['action']=='send'
    result=dict(command_id=legacy,state='succeeded',project_id=p['project_id'],subscription_id=None,revision=None,
                updated_at='2026-10-15T00:00:01Z',error_code=None,request_id=uid())
    done=call(domain,'outbox_result',principal=None,source='tracking',target=legacy,
              body={'lease_token':item['lease_token'],'outcome':'received','result':result})[1]
    assert done['state']=='succeeded'
    assert call(domain,'command',target=legacy)[1]['state']=='succeeded'

def test_outbox_claim_bumps_updated_at_for_fairness(domain):
    # Two pending rows; claiming the older one must not keep it forever at the head of ORDER BY updated_at.
    a=event();a['payload']['command_id']=uid('cmd_');a['payload']['source_entity_key']='fair-a';a['event_id']=uid('evt_');a['payload']['x_handle']='fair_a'
    b=event();b['payload']['command_id']=uid('cmd_');b['payload']['source_entity_key']='fair-b';b['event_id']=uid('evt_');b['payload']['x_handle']='fair_b';b['payload']['x_user_id']='999001'
    ra=call(domain,'ingest',principal=None,source='hunter',body=a)[1]
    rb=call(domain,'ingest',principal=None,source='hunter',body=b)[1]
    with domain.db.transaction() as con:
        con.execute("UPDATE tracking_outbox SET updated_at='2026-10-15T00:00:00.000000Z' WHERE command_id=?",(ra['command_id'],))
        con.execute("UPDATE tracking_outbox SET updated_at='2026-10-15T00:00:01.000000Z' WHERE command_id=?",(rb['command_id'],))
    first=call(domain,'outbox_claim',principal=None,source='tracking')[1]['item']
    assert first['command']['command_id']==ra['command_id']
    # While first is leased, second can still be claimed (different row).
    second=call(domain,'outbox_claim',principal=None,source='tracking')[1]['item']
    assert second['command']['command_id']==rb['command_id']
    # Release first as unknown; its updated_at was bumped on claim, so after lease expiry the other
    # completed/newer work stays ahead — re-seed a third pending with an older stamp and ensure
    # after claim+unknown the previously-claimed row is no longer strictly oldest.
    call(domain,'outbox_result',principal=None,source='tracking',target=ra['command_id'],
         body={'lease_token':first['lease_token'],'outcome':'unknown'})
    with domain.db.connect() as con:
        row=con.execute('SELECT updated_at,attempts FROM tracking_outbox WHERE command_id=?',(ra['command_id'],)).fetchone()
        assert row['attempts']>=1
        assert row['updated_at']>'2026-10-15T00:00:00.000000Z'

def test_ipc_boundary_and_error_envelopes(domain):
    cfg=IpcConfig(str(domain.db.path),'a'*64,'b'*40)
    with TestClient(create_ipc_app(cfg),raise_server_exceptions=False) as client:
        assert client.get('/health/ready').status_code==401
        auth={'Authorization':'Bearer '+cfg.token}
        assert client.get('/health/ready',headers=auth).json()['data']['writer']=='projects-domain'
        assert client.post('/v1/rpc',headers=auth,json={}).status_code==403
        headers={**auth,'X-Ikun-Build-Sha':cfg.build_sha}
        for path in ['/missing','/api/home/session']:
            response=client.get(path,headers=headers);assert response.status_code==404 and 'request_id' in response.json()
        response=client.post('/v1/rpc',headers=headers,json={'operation':'create','request_id':uid(),'principal':USER,'body':FIELDS,'idempotency_key':uid()})
        assert response.status_code==403 and response.json()['error']['code']=='FORBIDDEN'
        assert client.post('/v1/rpc',headers=headers,content=b'x'*131073).status_code==413
        assert client.post('/v1/rpc',headers=headers,content='not-json').status_code==422
        response=client.post('/v1/rpc',headers=headers,json={'operation':'list','request_id':uid(),'principal':USER})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'

def test_concurrent_confirmed_import_uses_one_canonical_id(domain):
    prototype=event()
    def ingest(index):
        data=copy.deepcopy(prototype);data['event_id']=uid('evt_');data['payload']['command_id']=uid('cmd_');data['payload']['x_handle']='renamed_'+str(index)
        return call(domain,'ingest',principal=None,source='hunter',body=data)[1]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(ingest,range(8)))
    assert len({r['project_id'] for r in results})==1
    with domain.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==8
        assert con.execute('SELECT COUNT(*) FROM tracking_outbox').fetchone()[0]==8

def test_command_conflict_rolls_back_new_event_and_sources(domain):
    data=event();call(domain,'ingest',principal=None,source='hunter',body=data)
    conflict=copy.deepcopy(data);conflict['event_id']=uid('evt_');conflict['payload']['source_entity_key']='new-alias';conflict['payload']['project']['notes']='different command'
    with pytest.raises(DomainError):call(domain,'ingest',principal=None,source='hunter',body=conflict)
    with domain.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==1
        assert not con.execute("SELECT 1 FROM project_sources WHERE external_id='new-alias'").fetchall()

def test_existing_alias_conflicting_website_requires_reconciliation(domain):
    data=event(website_url='https://first.example');call(domain,'ingest',principal=None,source='hunter',body=data)
    second=create(domain,website_url='https://second.example')
    conflict=copy.deepcopy(data);conflict['event_id']=uid('evt_');conflict['payload']['command_id']=uid('cmd_');conflict['payload']['project']['website_url']='https://second.example'
    with pytest.raises(DomainError) as exc:call(domain,'ingest',principal=None,source='hunter',body=conflict)
    assert exc.value.code=='CONFLICT'
    with domain.db.connect() as con:assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==1

def test_no_other_store_opened_or_modified(domain,tmp_path,monkeypatch):
    sentinels=[tmp_path/name for name in ('hunter.db','tracking.db','auth.db')]
    for path in sentinels:path.write_bytes(b'protected synthetic sentinel')
    before={path:path.stat().st_mtime_ns for path in sentinels};opened=[];connect=sqlite3.connect
    def guarded(path,*args,**kwargs):
        opened.append(str(path));assert 'projects.db' in str(path);return connect(path,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',guarded)
    p=create(domain);call(domain,'list');call(domain,'delete',target=p['project_id'],if_match='"rev-1"',idempotency_key=uid())
    assert opened and all(path.stat().st_mtime_ns==before[path] for path in sentinels)

def test_legacy_credentials_require_review_instead_of_copying_auth(domain,tmp_path):
    legacy=Database(tmp_path/'legacy/projects/projects.db');legacy.migrate();legacy.create_principal('superadmin')
    with pytest.raises(RuntimeError,match='LEGACY_IDENTITY_RETIREMENT_REQUIRED'):FormalDatabase(legacy.path).migrate()

@pytest.mark.parametrize('value',['2026-01-01T00:00:00Z',0,True])
def test_calendar_date_does_not_accept_timestamp(value):
    with pytest.raises(ValidationError):Fields.model_validate({**FIELDS,'token_date':value,'token_date_status':'confirmed'})


def test_hunter_first_discovered_at_is_preserved(domain):
    e=event();e['occurred_at']='2026-10-14T08:12:34.123Z'
    result=call(domain,'ingest',principal=None,source='hunter',body=e)[1]
    p=call(domain,'get',target=result['project_id'])[1]
    assert p['discovered_at']=='2026-10-14T08:12:34.123000Z'

def test_hunter_receipt_reports_command_outcome_without_writing(domain):
    data=event();created=call(domain,'ingest',principal=None,source='hunter',body=data)[1]
    assert created['command_state']=='pending' and created['error_code'] is None
    assert set(created)=={'event_id','project_id','receipt_id','accepted_at','duplicate','command_id','command_state','error_code'}
    with domain.db.connect() as con:
        before=[tuple(row) for row in con.execute('SELECT command_id,state,error_code,attempts,delivered FROM tracking_outbox')]
        assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==1
    plain_keys={'event_id','project_id','receipt_id','accepted_at','duplicate','command_id'}
    def read():return call(domain,'receipt',principal=None,source='hunter',target=data['event_id'])[1]
    assert set(read())-plain_keys=={'command_state','error_code'}
    cases=[('succeeded',None),('failed','ABANDONED_INVALID_ID_V5'),('failed','ABANDONED_DUPLICATE_CREATE_409'),('unknown','UPSTREAM_TIMEOUT'),('unknown','ownership_conflict'),('sending',None),('running',None)]
    for state,error in cases:
        with domain.db.transaction() as con:
            con.execute('UPDATE tracking_outbox SET state=?,error_code=? WHERE command_id=?',(state,error,created['command_id']))
        outcome=read()
        assert outcome['command_id']==created['command_id']
        assert outcome['command_state']==('pending' if state=='sending' else state)
        assert outcome['error_code']==error
        assert outcome['duplicate'] is True
    with domain.db.connect() as con:
        assert [tuple(row) for row in con.execute('SELECT command_id,attempts,delivered FROM tracking_outbox')]==[(before[0][0],before[0][3],before[0][4])]
        assert con.execute('SELECT COUNT(*) FROM tracking_outbox').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==1
