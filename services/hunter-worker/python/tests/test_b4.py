"""B4 local-only regression. Every provider and receiver is a strict fixture."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import importlib.util
import sys
import types
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from hunterradar.api import create_app
from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.formal import FormalService
from hunterradar.migration import APP_ID,FILES,SQL_ROOT,checksums,inspect,migrate,statements
from hunterradar.parsers import Target,wss_events
from hunterradar.protocol import Failure,Principal,ProjectFields,canonical
from hunterradar.providers import ProviderError,Providers
from hunterradar.store import Conflict,Store,WINDOW
from conftest import NOW,discover,event,ready

ADMIN=Principal(user_id='fixture-admin',tenant_id='ikun-main',role='superadmin')
USER=Principal(user_id='fixture-reader',tenant_id='ikun-main',role='user')
TOKEN='fixture-service-'+('x'*32)
def headers(actor=ADMIN):return {'authorization':'Bearer '+TOKEN,'x-ikun-principal':actor.model_dump_json()}
def client(store):return TestClient(create_app(Settings(db=store.path,v2_mode=True,admin_token=TOKEN),store=store),base_url='http://127.0.0.1')
def confirm(store,*,key=None,actor=ADMIN):
    service=FormalService(store);item=service.discovery(discover(store)['discovery_id'],NOW)
    status,command,_=service.write(actor,'POST','/api/v1/hunter/discoveries/'+item['discovery_id']+'/monitoring-requests',{'confirmed':True,'project':item['project']},key or str(uuid.uuid4()),f'"rev-{item["revision"]}"','fixture',NOW)
    return command,store.claim_task(NOW)

def test_no_implicit_init_or_ddl(tmp_path,store):
    path=tmp_path.resolve()/'unused'/'hunter.db'
    with pytest.raises(ValueError):Store(path)
    assert not path.parent.exists()
    with store.connect() as db:before=list(db.execute('SELECT sql FROM sqlite_master ORDER BY name'))
    with client(store) as c:assert c.get('/health/ready').status_code==200
    Store(store.path)
    with store.connect() as db:assert [tuple(r) for r in before]==[tuple(r) for r in db.execute('SELECT sql FROM sqlite_master ORDER BY name')]

@pytest.mark.parametrize('extended',[False,True])
def test_foundation_ledger_compatibility(tmp_path,extended):
    path=tmp_path.resolve()/'hunter.db'
    with sqlite3.connect(path) as db:
        statements(db,(SQL_ROOT/FILES[1]).read_text())
        if extended:db.execute('ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT NOT NULL')
        db.execute(f'PRAGMA application_id={APP_ID}')
        db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'hunter')")
        names='version,name,applied_at'+(',checksum' if extended else '')
        values=[1,'foundation','2026-10-15']+([checksums()[1]] if extended else [])
        db.execute(f"INSERT INTO _schema_migrations({names}) VALUES({','.join('?' for _ in values)})",values)
    os.chmod(path,0o600);migrate(path);migrate(path);inspect(path)
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM _migration_checksums').fetchone()[0]==len(FILES)

def test_candidate_upgrade_preserves_data(tmp_path):
    path=tmp_path.resolve()/'hunter.db'
    with sqlite3.connect(path) as db:
        statements(db,(SQL_ROOT/FILES[2]).read_text());db.execute(f'PRAGMA application_id={APP_ID}');db.execute('PRAGMA user_version=2')
        db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'hunter')")
        db.executemany('INSERT INTO _schema_migrations(version,name,applied_at) VALUES(?,?,?)',[(1,'foundation','old'),(2,'hunterradar_business','old')])
        db.execute('INSERT INTO _hunter_migrations(version,checksum,applied_at) VALUES(2,?,?)',(checksums()[2],'old'))
        db.execute('INSERT INTO hunters(id,username,created_at,note) VALUES(?,?,?,?)',('keep-id','fixture',NOW,'keep-notes'))
        db.execute('INSERT INTO discoveries(target,first_discovered_at,notes) VALUES(?,?,?)',('target',NOW,'preserved'))
        db.execute('INSERT INTO follow_events(event_key,hunter_id,hunter_x_id,generation,target,target_id,target_name,description,occurred_at,received_at,window_at,source,time_basis) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',('legacy-event','keep-id','101',1,'target','999','Target','',NOW,NOW,NOW,'6551_WSS','provider_event'))
    os.chmod(path,0o600);migrate(path)
    first=Store(path)
    assert first.hunters()[0]['id']=='keep-id' and first.discovery('target')['notes']=='preserved'
    identifier=first.discovery('target')['discovery_id'];migrate(path)
    assert Store(path).discovery('target')['discovery_id']==identifier

def test_migration_failure_rolls_back_and_recovers(tmp_path):
    path=tmp_path.resolve()/'hunter.db'
    with pytest.raises(ValueError,match='injected'):migrate(path,fail_before_commit=True)
    with sqlite3.connect(path) as db:assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==0
    migrate(path);inspect(path)

@pytest.mark.parametrize('tamper',["UPDATE _migration_checksums SET sha256='wrong' WHERE version=3",'PRAGMA user_version=99',"UPDATE _schema_migrations SET name='wrong' WHERE version=2"])
def test_wrong_checksum_version_refused(store,tamper):
    with store.connect() as db:db.execute(tamper)
    before=store.path.read_bytes()
    with pytest.raises(ValueError):migrate(store.path)
    assert store.path.read_bytes()==before
    with client(store) as c:assert c.get('/health/ready').status_code==503

@pytest.mark.parametrize('suffix',['-wal','-shm'])
def test_sidecar_hardlink_refused(tmp_path,suffix):
    folder=tmp_path.resolve();source=folder/'private';source.write_text('private');os.link(source,folder/('hunter.db'+suffix))
    with pytest.raises(ValueError,match='private_regular'):migrate(folder/'hunter.db')
    assert source.read_text()=='private'

def test_backup_restore_new_path(store,tmp_path):
    discover(store);directory=tmp_path.resolve()/'restored';directory.mkdir(mode=0o700);destination=directory/'hunter.db'
    with store.connect() as db,sqlite3.connect(destination) as target:db.backup(target)
    os.chmod(destination,0o600)
    restored=Store(destination)
    assert restored.discovery('project1')['discovery_id']==store.discovery('project1')['discovery_id']

def test_target_rename_stable_and_conflict_rejected(store):
    ready(store,'hunter1',user_id='101');ready(store,'hunter2',user_id='102')
    assert store.ingest_wss(event(target='before',target_id='999'))
    assert store.ingest_wss(event('hunter2',target='after',target_id='999'))
    item=FormalService(store).page('signals',{},NOW)['items'][0]
    assert item['x_handle']=='after' and item['signal_count']==2
    assert not store.ingest_wss(event('hunter2',target='before',target_id='999'))
    assert FormalService(store).page('signals',{},NOW)['items'][0]['discovery_id']==item['discovery_id']
    with pytest.raises(Conflict):store.ingest_wss(event('hunter2',target='after',target_id='123',at=NOW+1))
    with store.connect() as db:assert db.execute('SELECT count(*) FROM discoveries').fetchone()[0]==1

def test_wss_new_generation_baseline_fences_history(store):
    row=store.add('hunter1',now=NOW-100);store.apply_profile(row,'101','Hunter',5000,NOW-50)
    row=store.hunter(row['id']);assert not store.ingest_wss(event(at=NOW-1))
    store.establish_wss_baseline([row],NOW)
    assert not store.ingest_wss(event(at=NOW-1)) and store.ingest_wss(event())
    disabled=store.patch(row['id'],row['version'],enabled=False,now=NOW+1)
    store.establish_wss_baseline([row],NOW+2)
    assert not store.hunter(row['id'])['baseline_ready']

@pytest.mark.parametrize('bad_time',[True,float('nan'),float('inf'),None])
def test_missing_or_invalid_time_not_fabricated(bad_time):
    payload={'method':'twitter.event','params':{'eventType':'NEW_FOLLOWER','twAccount':'hunter1','createdAt':bad_time,'content':[{'twAccount':'project1'}]}}
    with pytest.raises((ValueError,TypeError)):wss_events(payload,NOW)

def test_rest_interval_is_3600_from_last_success(store):
    row=ready(store,followers=4999)
    store.apply_poll(row,[],NOW+121)
    assert store.hunter(row['id'])['next_poll_at']==NOW+121+3600

async def test_rest_same_account_no_concurrent_reentry(store):
    row=ready(store,followers=4999);calls=[]
    class Fixture:
        async def request(self,*args):calls.append(args);await asyncio.sleep(.02);return {'followings':[]}
    engine=Engine(Settings(db=store.path),store,Fixture())
    await asyncio.gather(engine.poll(row),engine.poll(row))
    assert len(calls)==1

async def test_billing_unknown_persistent_no_auto_paid_retry(store):
    calls=[]
    async def fixture(request):calls.append(request);raise httpx.ReadTimeout('fixture')
    settings=Settings(db=store.path,external_io_enabled=True,token_6551='synthetic-only')
    async with httpx.AsyncClient(transport=httpx.MockTransport(fixture)) as c:
        p=Providers(settings,store,c)
        for provider in (p,Providers(settings,Store(store.path),c)):
            with pytest.raises(ProviderError,match='billing_unknown'):await provider.request('profile','fixture')
    assert len(calls)==1 and store.status()['daily_reserved']['6551']==1

async def test_profile_stable_identity_conflict_stops_generation(store):
    row=ready(store)
    class Fixture:
        async def request(self,*args):return {'data':{'screenName':'hunter1','id':'777','followersCount':5000}}
    engine=Engine(Settings(db=store.path),store,Fixture());await engine.scan_profile(row)
    current=store.hunter(row['id'])
    assert current['profile_status']=='pending' and current['generation']>row['generation'] and current['next_profile_at']==9999999999
    assert current['profile_error']=='stable_identity_conflict' and not store.ingest_wss(event())

def test_standard_api_permissions_and_hunter_crud(store):
    body={'x_handle':'fixture_hunter','label':'Fixture','notes':'private admin','enabled':False};key=str(uuid.uuid4())
    with client(store) as c:
        assert c.get('/api/v1/hunter/signals').status_code==401
        assert c.get('/api/v1/hunter/accounts',headers=headers(USER)).status_code==403
        assert c.post('/api/v1/hunter/accounts',json=body,headers=headers(USER)|{'idempotency-key':key}).status_code==403
        result=c.post('/api/v1/hunter/accounts',json=body,headers=headers()|{'idempotency-key':key})
        assert result.status_code==201 and result.headers['cache-control']=='no-store'
        data=result.json()['data'];assert data['connection']=='unconfigured' and not data['enabled']
        assert c.post('/api/v1/hunter/accounts',json=body,headers=headers()|{'idempotency-key':key}).json()['data']==data
        assert c.post('/api/v1/hunter/accounts',json=body|{'label':'changed'},headers=headers()|{'idempotency-key':key}).status_code==409
        path='/api/v1/hunter/accounts/'+data['account_id']
        assert c.patch(path,json={'enabled':True},headers=headers()|{'idempotency-key':str(uuid.uuid4())}).status_code==428
        changed=c.patch(path,json={'enabled':True,'label':'updated','notes':'note'},headers=headers()|{'idempotency-key':str(uuid.uuid4()),'if-match':result.headers['etag']})
        assert changed.status_code==200 and changed.json()['data']['enabled']
        deleted=c.delete(path,headers=headers()|{'content-type':'application/json','idempotency-key':str(uuid.uuid4()),'if-match':changed.headers['etag']})
        assert deleted.status_code==200 and deleted.json()['data']=={'account_id':data['account_id'],'removed':True}
    assert store.hunters()==[]

@pytest.mark.parametrize('invalid',[{}, {'user_id':'forged','tenant_id':'other','role':'superadmin'},{'user_id':'forged','tenant_id':'ikun-main','role':'admin'}])
def test_service_and_principal_both_required(store,invalid):
    with client(store) as c:
        result=c.get('/api/v1/hunter/signals',headers={'authorization':'Bearer '+TOKEN,'x-ikun-principal':json.dumps(invalid),'x-role':'superadmin','x-tenant':'ikun-main'})
        assert result.status_code==403

def test_confirmation_atomic_ids_receipt_and_privacy(store):
    service=FormalService(store);dto=service.discovery(discover(store)['discovery_id'],NOW);key=str(uuid.uuid4())
    path='/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests';body={'confirmed':True,'project':dto['project']}
    args=(ADMIN,'POST',path,body,key,f'"rev-{dto["revision"]}"','test-id',NOW)
    first=service.write(*args);assert service.write(*args)==first
    command=first[1];assert first[0]==202 and command['project_id'] is None and command['state']=='pending'
    task=store.claim_task(NOW);event_data=json.loads(task['body'])
    assert event_data['payload']['command_id']==command['command_id'] and event_data['event_type']=='hunter.monitoring_requested'
    assert event_data['payload']['discovery_id']==dto['discovery_id'] and event_data['tenant_id']=='ikun-main'
    raw=canonical(service.discovery(dto['discovery_id'],NOW));assert 'hunter1' not in raw and 'hunter2' not in raw and 'raw_payload' not in raw and TOKEN not in raw
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM task_outbox').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM operation_receipts').fetchone()[0]==1
    with pytest.raises(Failure) as changed:service.write(ADMIN,'POST',path,body|{'confirmed':False},key,f'"rev-{dto["revision"]}"','test-id',NOW)
    assert changed.value.code=='IDEMPOTENCY_CONFLICT'

def test_confirmation_rollback_leaves_no_revision_or_task(store,monkeypatch):
    service=FormalService(store);dto=service.discovery(discover(store)['discovery_id'],NOW)
    def fail(*args,**kwargs):raise RuntimeError('injected audit failure')
    monkeypatch.setattr(store,'audit',fail)
    with pytest.raises(RuntimeError):service.write(ADMIN,'POST','/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests',{'confirmed':True,'project':dto['project']},str(uuid.uuid4()),f'"rev-{dto["revision"]}"','test',NOW)
    assert service.discovery(dto['discovery_id'],NOW)['revision']==dto['revision']
    with store.connect() as db:assert db.execute('SELECT count(*) FROM task_outbox').fetchone()[0]==0

@pytest.mark.parametrize('query',[{'cursor':''},{'cursor':'broken'},{'limit':'101'},{'since':'2026-10-15'},{'offset':'0'},{'rating':'fake'},{'tenant_id':'other'}])
def test_cursor_invalid_query_refused(store,query):
    with pytest.raises(Failure):FormalService(store).page('signals',query,NOW)

def test_database_keyset_pagination_and_query_binding(store):
    ready(store,'hunter1',user_id='101');ready(store,'hunter2',user_id='102')
    for index in range(107):
        for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,target='target'+str(index),target_id=str(1000+index),at=NOW-index,key=hunter+str(index)))
    service=FormalService(store);first=service.page('signals',{'limit':'100'},NOW);assert len(first['items'])==100 and first['next_cursor']
    second=service.page('signals',{'limit':'100','cursor':first['next_cursor']},NOW);assert len(second['items'])==7 and second['next_cursor'] is None
    assert len({row['discovery_id'] for row in first['items']+second['items']})==107
    with pytest.raises(Failure):service.page('signals',{'limit':'100','q':'changed','cursor':first['next_cursor']},NOW)

async def test_lost_ack_only_reconciles_original_event(store):
    command,task=confirm(store);posted=[];receipt=None
    project='prj_'+str(uuid.uuid4())
    async def receiver(request):
        nonlocal receipt
        if request.method=='GET':return httpx.Response(404) if receipt is None else httpx.Response(200,json={'data':receipt})
        posted.append(json.loads(request.content));receipt={'event_id':task['event_id'],'command_id':task['command_id'],'project_id':project,'receipt_id':'fixture-receipt','accepted_at':'2026-10-15T00:00:00Z','duplicate':True}
        raise httpx.ReadTimeout('lost ack')
    settings=Settings(db=store.path,project_url='http://127.0.0.1/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='fixture-receiver-'+('z'*32))
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as c:
        await Engine(settings,store,Providers(settings,store,c)).deliver(task)
        recovered=Store(store.path);recovered.recover();again=recovered.claim_task(NOW+1000)
        await Engine(settings,recovered,Providers(settings,recovered,c)).deliver(again)
    assert len(posted)==1 and posted[0]['event_id']==task['event_id']
    actual=FormalService(store).command(command['command_id'],'query')
    assert actual['project_id']==project and actual['state']=='pending' and actual['subscription_id'] is None

@pytest.mark.parametrize('mismatch',['command_id','event_id','accepted_at','project_id'])
async def test_malformed_receipt_no_false_success(store,mismatch):
    command,task=confirm(store)
    receipt={'event_id':task['event_id'],'command_id':task['command_id'],'project_id':'prj_'+str(uuid.uuid4()),'receipt_id':'receipt','accepted_at':'2026-10-15T00:00:00Z','duplicate':False};receipt[mismatch]='invalid'
    calls=[]
    async def receiver(request):calls.append(request.method);return httpx.Response(200,json={'data':receipt})
    settings=Settings(db=store.path,project_url='http://127.0.0.1/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='f'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as c:await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    assert calls==['GET'] and FormalService(store).command(command['command_id'],'query')['state']=='unknown'

def test_internal_unimplemented_and_c04_requires_revision(store):
    dto=FormalService(store).discovery(discover(store)['discovery_id'],NOW)
    with client(store) as c:
        assert c.post('/internal/v1/commands',json={},headers=headers()).status_code==501
        r=c.patch('/api/v1/hunter/discoveries/'+dto['discovery_id'],json={'name':'no'},headers=headers()|{'idempotency-key':str(uuid.uuid4())})
        assert r.status_code==428 and r.json()['error']['code']=='VALIDATION_ERROR'
        assert c.get('/api/hunterradar/v1/hunters',headers=headers()).status_code==404

@pytest.mark.parametrize('changes',[{'admin_token':'short'},{'tenant_id':'other'},{'host':'0.0.0.0'},{'admin_token':'a'*32,'project_token':'a'*32},{'project_url':'http://127.0.0.1/internal/v1/ingest/tracking','delivery_protocol':'v2-event','project_token':'p'*32}])
def test_formal_settings_closed_on_bad_scope_or_tokens(changes):
    with pytest.raises(ValueError):Settings(v2_mode=True,**changes)

async def test_posted_event_with_missing_receipt_never_blind_reposts(store):
    command,task=confirm(store);calls=[]
    async def receiver(request):calls.append(request.method);return httpx.Response(404)
    with store.connect(True) as db:db.execute('UPDATE task_outbox SET posted=1 WHERE id=?',(task['id'],))
    store.recover();task=store.claim_task(NOW+1)
    settings=Settings(db=store.path,project_url='http://127.0.0.1/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='f'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as c:await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    assert calls==['GET'] and FormalService(store).command(command['command_id'],'query')['state']=='unknown'

async def test_429_cooldown_is_persistent_and_honors_retry_after(store):
    calls=[]
    async def fixture(request):calls.append(request);return httpx.Response(429,headers={'retry-after':'120'})
    settings=Settings(db=store.path,external_io_enabled=True,token_6551='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(fixture)) as c:
        with pytest.raises(ProviderError,match='rate_limited') as failure:await Providers(settings,store,c).request('profile','fixture')
        assert failure.value.retry_after==120
        with pytest.raises(ProviderError,match='cooldown'):await Providers(settings,Store(store.path),c).request('profile','fixture')
    assert len(calls)==1

async def test_wss_reconnect_duplicate_and_malformed_frames(store):
    from test_core import payload
    ready(store,'hunter1',user_id='101');ready(store,'hunter2',user_id='102')
    engine=Engine(Settings(db=store.path,token_6551='synthetic'),store)
    class Socket:
        def __init__(self):self.frames=[json.dumps({'id':1,'result':{'success':True}}),'not-json','[]',json.dumps(payload()),json.dumps(payload(twAccount='hunter2',id='second'))]
        async def send(self,message):assert 'twitter.subscribe' in message
        async def recv(self):
            if self.frames:return self.frames.pop(0)
            engine.stop.set();return 'pong'
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    engine.connector=lambda *args,**kwargs:Socket()
    try:
        await engine.consume();engine.stop.clear();await engine.consume()
        assert store.status()['events']==2 and len(store.discoveries())==1
        assert store.states()['last_rejected_event_at'] and store.states()['last_pong_at']
    finally:await engine.providers.close()

async def test_ack_without_heartbeat_never_claims_connected(store):
    from hunterradar.formal import account_dto
    row=ready(store)
    with store.connect(True) as db:db.execute('UPDATE hunters SET watch_covered=1 WHERE id=?',(row['id'],))
    store.set_state('worker_heartbeat',time.time());store.set_state('wss_state','subscribed');store.set_state('last_pong_at',None)
    with store.connect() as db:assert account_dto(db,store.hunter(row['id']),time.time())['connection']=='disconnected'
    store.set_state('last_pong_at',time.time())
    with store.connect() as db:assert account_dto(db,store.hunter(row['id']),time.time())['connection']=='connected'

def test_rediscovery_window_does_not_create_second_record(store):
    first=discover(store);later=NOW+WINDOW+100
    assert FormalService(store).page('signals',{},later)['items']==[]
    for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,at=later,received=later))
    again=FormalService(store).page('signals',{},later)['items'][0]
    assert again['discovery_id']==first['discovery_id']
    with store.connect() as db:assert db.execute('SELECT count(*) FROM discoveries').fetchone()[0]==1

def test_uuid_key_scope_is_actor_and_route_not_global(store):
    service=FormalService(store);item=discover(store);key=str(uuid.uuid4());other=Principal(user_id='another_admin',tenant_id='ikun-main',role='superadmin')
    for target,actor in [('project1',ADMIN),('project2',other)]:
        if target=='project2':
            for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,target=target,target_id='888'))
        with store.connect() as db:identifier=db.execute('SELECT discovery_id FROM discoveries WHERE target=?',(target,)).fetchone()[0]
        dto=service.discovery(identifier,NOW)
        service.write(actor,'POST','/api/v1/hunter/discoveries/'+identifier+'/monitoring-requests',{'confirmed':True,'project':dto['project']},key,f'"rev-{dto["revision"]}"','fixture',NOW)
    with store.connect() as db:assert db.execute('SELECT count(*) FROM task_outbox').fetchone()[0]==2

def test_confirmed_null_grade_does_not_fall_back_to_old_rating(store):
    from conftest import reviewed
    service=FormalService(store);dto=service.discovery(reviewed(store)['discovery_id'],NOW)
    body={'confirmed':True,'project':dict(dto['project'],rating=None)}
    service.write(ADMIN,'POST','/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests',body,str(uuid.uuid4()),f'"rev-{dto["revision"]}"','fixture',NOW)
    assert len(service.page('signals',{'rating':'unrated'},NOW)['items'])==1
    assert service.page('signals',{'rating':'A'},NOW)['items']==[]

def test_secret_file_supports_distinct_direction_tokens_without_provider_io(tmp_path,monkeypatch):
    for key in list(os.environ):
        if key.startswith(('HUNTER_','OPENNEWS_','TWITTERAPI_','PROJECTS_INGEST_HUNTER')):monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    secret=tmp_path/'fixture-secrets';secret.write_text('HUNTER_API_TOKEN='+('h'*32)+'\nPROJECTS_INGEST_HUNTER_TOKEN='+('p'*32)+'\n')
    monkeypatch.setenv('HUNTER_SECRETS_FILE',str(secret));monkeypatch.setenv('HUNTER_V2_MODE','1')
    settings=Settings.load();assert settings.admin_token=='h'*32 and settings.project_token=='p'*32
    assert not settings.external_io_enabled and not settings.project_delivery_enabled
    assert settings.admin_token not in repr(settings) and settings.project_token not in repr(settings)

def test_formal_api_rejects_all_user_mutations_and_old_offset(store):
    dto=FormalService(store).discovery(discover(store)['discovery_id'],NOW)
    paths=[('/api/v1/hunter/accounts','POST'),('/api/v1/hunter/accounts/unknown','PATCH'),('/api/v1/hunter/accounts/unknown','DELETE'),('/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests','POST')]
    with client(store) as c:
        for path,method in paths:assert c.request(method,path,json={},headers=headers(USER)).status_code==403
        response=c.get('/api/v1/hunter/signals?offset=0',headers=headers(USER));assert response.status_code==422
        assert response.headers['x-request-id']==response.json()['request_id'] and isinstance(response.json()['error']['retryable'],bool)

@pytest.mark.parametrize('grade',['S','A','B','C','D',None])
def test_actual_frozen_b2_accepts_serialized_monitoring_event(store,tmp_path,grade):
    # Consume only immutable models/transport source as a test dependency. No Projects DB.
    root=Path(__file__).resolve().parents[4]
    commit='d0fdefab2aa230ebb8df856aed306d0184d362e2'
    package='hunter_b2_contract_fixture';module=types.ModuleType(package);module.__path__=[str(tmp_path)];sys.modules[package]=module
    for name in ('models','transport'):
        data=subprocess.check_output(['git','show',commit+':modules/projects/candidate/projects_service/'+name+'.py'],cwd=root)
        path=tmp_path/(name+'.py');path.write_bytes(data)
        spec=importlib.util.spec_from_file_location(package+'.'+name,path);loaded=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loaded;spec.loader.exec_module(loaded)
    command,task=confirm(store);payload=json.loads(task['body']);payload['payload']['project']['rating']=grade
    parsed=loaded.Event.model_validate(payload)
    serialized=parsed.model_dump(mode='json')
    assert serialized['payload']['command_id']==command['command_id']
    assert parsed.payload.project.core().rating==(grade or 'unrated')
    assert set(serialized['payload'])=={'command_id','discovery_id','source_entity_key','confirmed','actor','project','x_user_id','x_handle'}
