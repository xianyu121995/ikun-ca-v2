import asyncio
import hashlib
import hmac
import json
import time
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hunterradar.api import PREFIX, create_app
from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.gateway import GatewaySettings, install_hunterradar_gateway
from hunterradar.providers import ProviderError, Providers
from integration.receiver_contract import verify
from conftest import NOW, discover, ready, reviewed

ADMIN='a'*40
VIEW='v'*40


def client(store, **settings):
    return TestClient(create_app(Settings(db=store.path,admin_token=ADMIN,view_token=VIEW,**settings),store=store),base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+ADMIN})


def test_api_hunter_crud_and_conflict(store):
    with client(store) as c:
        row=c.post(PREFIX+'/hunters',json={'username':'@Hunter1','note':'watch'}).json()
        assert row['profile_status']=='pending'
        assert c.patch(PREFIX+'/hunters/'+row['id'],json={'expected_version':1,'note':'updated'}).status_code==200
        assert c.patch(PREFIX+'/hunters/'+row['id'],json={'expected_version':1,'enabled':False}).status_code==409
        assert c.post(PREFIX+'/hunters/'+row['id']+'/recheck',json={'expected_version':2}).status_code==200
        assert c.delete(PREFIX+'/hunters/'+row['id']+'?expected_version=3').status_code==200
        assert c.get(PREFIX+'/hunters').json()['items']==[]


def test_api_viewer_privacy_and_auth(store):
    discover(store)
    with client(store) as c:
        c.headers['Authorization']='Bearer '+VIEW
        assert c.get(PREFIX+'/hunters').status_code==403
        assert c.post(PREFIX+'/hunters',json={'username':'new'}).status_code==403
        response=c.get(PREFIX+'/signals')
        assert response.status_code==200 and response.json()['items'][0]['hunter_count']==2
        assert 'hunter1' not in response.text and 'hunter2' not in response.text
        assert c.get(PREFIX+'/session').json()['can_manage'] is False
        del c.headers['Authorization']
        assert c.get(PREFIX+'/status').status_code==401
        assert c.get('/health').status_code==200


def test_csrf_and_inputs(store):
    with client(store) as c:
        assert c.post(PREFIX+'/hunters',json={'username':'hunter1'},headers={'Origin':'https://evil.example'}).status_code==403
        for body in ({'username':'../../bad'},{'username':'h','private_key':'secret'}):
            assert c.post(PREFIX+'/hunters',json=body).status_code==422
        assert c.get(PREFIX+'/assets/secret').status_code==404


def test_api_review_and_confirmation(store):
    discover(store)
    with client(store) as c:
        assert c.post(PREFIX+'/discoveries/project1/confirm',json={'expected_version':1,'confirmed':False},headers={'Idempotency-Key':'manual1'}).status_code==422
        response=c.put(PREFIX+'/discoveries/project1/review',json={'expected_version':1,'name':'Project','rating':'A','notes':'verified'})
        version=response.json()['version']
        task=c.post(PREFIX+'/discoveries/project1/confirm',json={'expected_version':version,'confirmed':True},headers={'Idempotency-Key':'manual1'})
        assert task.status_code==202 and task.json()['status']=='pending'
        assert c.post(PREFIX+'/discoveries/project1/confirm',json={'expected_version':version,'confirmed':True},headers={'Idempotency-Key':'manual1'}).json()['id']==task.json()['id']


def test_page_and_assets_have_security_headers(store):
    with client(store) as c:
        for path in ('/hunterradar',PREFIX+'/page',PREFIX+'/assets/app.js',PREFIX+'/assets/style.css'):
            response=c.get(path)
            assert response.status_code==200
            assert response.headers['cache-control']=='no-store'
            assert "frame-ancestors 'self'" in response.headers['content-security-policy']
        assert '项目发现' in c.get('/hunterradar').text


async def test_provider_request_contract_and_budget(store):
    calls=[]
    async def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'followings':[],'status':'success'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=Providers(Settings(db=store.path,token_twitterapi='key',external_io_enabled=True),store,c)
        await p.request('followings','hunter1')
    assert calls[0].url.path=='/twitter/user/followings'
    assert dict(calls[0].url.params)=={'userName':'hunter1','cursor':'','pageSize':'20'}
    assert calls[0].headers['x-api-key']=='key'
    assert store.status()['daily_reserved']['twitterapi']==60


@pytest.mark.parametrize('status,code', [(401,'provider_auth_failed'),(403,'provider_auth_failed'),(429,'provider_rate_limited'),(500,'provider_http_500')])
async def test_provider_errors_sanitized_and_charged(store,status,code):
    async def handler(request):
        return httpx.Response(status,text='secret=DO_NOT_LEAK',headers={'Retry-After':'120'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=Providers(Settings(db=store.path,token_6551='secret',external_io_enabled=True),store,c)
        with pytest.raises(ProviderError) as caught:
            await p.request('profile','hunter1')
        assert str(caught.value)==code
    assert store.status()['daily_reserved']['6551']==1


async def test_account_failure_keeps_baseline_and_retry(store):
    row=ready(store,followers=10)
    async def handler(request):
        raise httpx.ReadTimeout('secret token in url')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        providers=Providers(Settings(db=store.path,token_twitterapi='secret',external_io_enabled=True),store,c)
        engine=Engine(providers.settings,store,providers)
        await engine.poll(row)
    updated=store.hunter(row['id'])
    assert not updated['baseline_ready'] and updated['poll_failures']==1
    assert updated['next_poll_at']>time.time() and 'secret' not in updated['poll_error']


async def test_rest_accounts_isolated(store):
    rows=[ready(store,'hunter'+str(i),followers=10,user_id=str(100+i)) for i in (1,2)]
    async def handler(request):
        if request.url.params['userName']=='hunter1':
            return httpx.Response(500)
        return httpx.Response(200,json={'followings':[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        settings=Settings(db=store.path,token_twitterapi='key',external_io_enabled=True)
        engine=Engine(settings,store,Providers(settings,store,c))
        await asyncio.gather(*(engine.poll(row) for row in rows))
    assert store.hunter(rows[0]['id'])['poll_failures']==1
    assert store.hunter(rows[1]['id'])['baseline_ready']==1


async def test_manual_outbox_signature_and_receipt(store):
    item=reviewed(store)
    store.confirm('project1',item['version'],'key','admin',NOW)
    task=store.claim_task(NOW)
    captured=[]
    async def handler(request):
        command=verify(request.content,request.headers,'s'*32)
        captured.append(command)
        return httpx.Response(202,json={'accepted':True,'command_id':command['command_id'],'task_id':'project-task-123'})
    settings=Settings(db=store.path,project_url='http://127.0.0.1:9000/tasks',project_secret='s'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        engine=Engine(settings,store,Providers(settings,store,c))
        await engine.deliver(task)
    result=store.discovery('project1')['task']
    assert result['status']=='delivered' and result['receipt_id']=='project-task-123'
    assert 'hunter1' not in json.dumps(captured)


@pytest.mark.parametrize('status,body,result', [(200,{'accepted':True,'task_id':'t'},'failed'),(403,{},'failed'),(503,{},'pending'),(302,{},'failed')])
async def test_outbox_does_not_claim_false_delivery(store,status,body,result):
    item=reviewed(store)
    store.confirm('project1',item['version'],'key','admin',NOW)
    task=store.claim_task(NOW)
    settings=Settings(db=store.path,project_url='http://127.0.0.1:9000/tasks',project_secret='s'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(status,json=body))) as c:
        await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    assert store.discovery('project1')['task']['status']==result


async def test_outbox_timeout_keeps_stable_command_id(store):
    item=reviewed(store)
    store.confirm('project1',item['version'],'key','admin',NOW)
    task=store.claim_task(NOW)
    async def handler(request):
        raise httpx.ReadTimeout('ambiguous remote success')
    settings=Settings(db=store.path,project_url='http://127.0.0.1:9000/tasks',project_secret='s'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    replay=store.claim_task(time.time()+4000)
    assert replay['id']==task['id'] and replay['idempotency_key']==task['idempotency_key']


async def test_worker_start_stop_and_heartbeat(store):
    settings=Settings(db=store.path)
    engine=Engine(settings,store)
    task=asyncio.create_task(engine.run())
    await asyncio.sleep(.15)
    assert store.status()['worker_alive']
    engine.stop.set()
    await asyncio.wait_for(task,2)
    assert not store.status()['worker_alive']


async def test_wss_ack_and_direction_through_engine(store):
    from test_core import payload
    ready(store)
    ready(store,'hunter2',user_id='102')
    engine=Engine(Settings(db=store.path,token_6551='token'),store)
    class Socket:
        def __init__(self):
            self.messages=[json.dumps({'id':1,'result':{'success':True}}),json.dumps(payload()),json.dumps(payload(twAccount='hunter2',id='e2'))]
        async def send(self,message):
            assert 'twitter.subscribe' in message
        async def recv(self):
            if not self.messages:
                engine.stop.set()
                return 'pong'
            return self.messages.pop(0)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    engine.connector=lambda *args,**kwargs:Socket()
    await engine.consume()
    assert store.states()['wss_state']=='subscribed'
    assert store.aggregate(NOW)[0]['hunter_count']==2
    await engine.providers.close()


async def test_gateway_real_authorization_and_no_credential_leak(store):
    discover(store)
    target=create_app(Settings(db=store.path,admin_token=ADMIN,view_token=VIEW),store=store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target),base_url='http://127.0.0.1') as upstream:
        host=FastAPI()
        async def authorize(request,capability):
            role=request.cookies.get('test_session')
            return 'real-actor-id' if role=='admin' or role=='viewer' and capability=='hunter.read' else None
        install_hunterradar_gateway(host,GatewaySettings(admin_token=ADMIN,view_token=VIEW),authorize,upstream)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host),base_url='http://website') as c:
            assert (await c.get(PREFIX+'/signals')).status_code==403
            c.cookies.set('test_session','viewer')
            assert (await c.get(PREFIX+'/signals')).status_code==200
            assert (await c.get(PREFIX+'/hunters')).status_code==403
            session=(await c.get(PREFIX+'/session')).json()
            assert session['role']=='user'
            assert ADMIN not in json.dumps(session) and VIEW not in json.dumps(session)
            c.cookies.set('test_session','admin')
            assert (await c.post(PREFIX+'/hunters',json={'username':'third'})).status_code==201
            assert (await c.get(PREFIX+'/hunters')).status_code==200
            assert (await c.post(PREFIX+'/hunters',json={'username':'fourth'},headers={'Origin':'http://evil'})).status_code==403

async def test_external_io_is_off_by_default_even_with_credentials(store):
    calls=[]
    async def handler(request):
        calls.append(request)
        return httpx.Response(200,json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        p=Providers(Settings(db=store.path,token_6551='configured'),store,c)
        with pytest.raises(ProviderError,match='external_io_disabled'):
            await p.request('profile','hunter1')
    assert calls==[]


async def test_v2_reconcile_before_post_and_canonical_receipt(store):
    item=reviewed(store)
    from hunterradar.formal import FormalService
    from hunterradar.protocol import Principal
    service=FormalService(store);dto=service.discovery(item['discovery_id'])
    service.write(Principal(user_id='admin',tenant_id='ikun-main',role='superadmin'),'POST','/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests',{'confirmed':True,'project':dto['project']},str(uuid.uuid4()),f'"rev-{dto["revision"]}"','fixture',NOW)
    task=store.claim_task(NOW)
    calls=[]
    project_id='prj_00000000-0000-4000-8000-000000000001'
    async def handler(request):
        calls.append(request.method)
        if request.method=='GET':return httpx.Response(404)
        body=json.loads(request.content)
        assert body['tenant_id']=='ikun-main' and body['project_id'] is None
        assert body['event_type']=='hunter.monitoring_requested' and body['payload']['confirmed'] is True
        assert request.headers['authorization']=='Bearer '+'t'*32
        assert 'hunter1' not in request.content.decode()
        return httpx.Response(200,json={'data':{'event_id':body['event_id'],'command_id':body['payload']['command_id'],'project_id':project_id,'receipt_id':'receipt1','accepted_at':'2026-10-15T00:00:00Z','duplicate':False}})
    settings=Settings(db=store.path,project_url='http://127.0.0.1:9000/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='t'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    assert calls==['GET','POST']
    assert store.discovery('project1')['task']['project_id']==project_id


async def test_v2_unknown_receipt_does_not_resend(store):
    item=reviewed(store)
    from hunterradar.formal import FormalService
    from hunterradar.protocol import Principal
    service=FormalService(store);dto=service.discovery(item['discovery_id'])
    service.write(Principal(user_id='admin',tenant_id='ikun-main',role='superadmin'),'POST','/api/v1/hunter/discoveries/'+dto['discovery_id']+'/monitoring-requests',{'confirmed':True,'project':dto['project']},str(uuid.uuid4()),f'"rev-{dto["revision"]}"','fixture',NOW)
    task=store.claim_task(NOW)
    calls=[]
    async def handler(request):
        calls.append(request.method)
        raise httpx.ReadTimeout('cannot reconcile')
    settings=Settings(db=store.path,project_url='http://127.0.0.1:9000/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='t'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await Engine(settings,store,Providers(settings,store,c)).deliver(task)
    assert calls==['GET'] and store.discovery('project1')['task']['status']=='unknown'


def test_v2_health_and_closed_auth(store):
    app=create_app(Settings(db=store.path,v2_mode=True),store=store)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        health=c.get('/health/ready')
        assert health.status_code==200 and 'data' in health.json()
        assert 'request_id' in health.json() and 'x-request-id' in health.headers
        assert c.get('/internal/v1/status').status_code==503
        assert c.get('/internal/v1/status').json()['error']['retryable'] is False
        assert c.get(PREFIX+'/hunters').status_code==503
