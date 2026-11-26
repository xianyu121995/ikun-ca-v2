import sys
from pathlib import Path
root=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(root/'services/tracking-worker/python'),str(root/'services/hunter-worker/python')]
import httpx
import pytest
from tracking.config import Config
from tracking.remote import Remote, RemoteError
from hunterradar.config import Settings
from hunterradar.providers import Providers
from hunterradar.store import Store
from provider_6551 import Ledger


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('IKUN_TRACKING_BACKFILL_ENABLED','1')
    monkeypatch.setenv('IKUN_6551_BACKFILL_DAILY_LIMIT','300')
    monkeypatch.setenv('IKUN_6551_LEDGER',str(tmp_path/'ops/ledger.db'))
    monkeypatch.setenv('IKUN_TRACKING_X_BEARER_TOKEN','PRIVATE_TOKEN')
    cfg=Config(db_path=tmp_path/'tracking/tracking.db',remote_enabled=True,dedicated_account=True,request_interval=0)
    store=Store(tmp_path/'hunter/hunter.db',initialize=True)
    settings=Settings(db=store.path,external_io_enabled=True,token_6551='PRIVATE_TOKEN')
    return cfg,store,settings


async def test_tracking_x_payment_does_not_close_the_6551_ledger(setup):
    cfg,store,settings=setup;calls=[]
    def transport(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/rules'):
            return httpx.Response(402,json={'title':'Payment Required','status':402})
        return httpx.Response(200,json={'success':True,'data':[]})
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        hunter=Providers(settings,store,client)
        with pytest.raises(RemoteError,match='provider_payment_required'):await remote.watches()
        assert await hunter.request('watch')=={'success':True,'data':[]}
        assert remote.ledger.summary()['quota_exhausted'] is False
        assert calls==['/2/tweets/search/stream/rules','/open/twitter_watch']
    await remote.close()


async def test_watch_rules_are_not_the_shared_6551_snapshot(setup):
    cfg,store,settings=setup;calls=[]
    payload={'success':True,'data':[{'twAccount':'example','newTweetBol':True}]}
    rules={'data':[{'id':'1','value':'from:example -is:retweet -is:reply','tag':'ikun-ca-v2:tracking:example'}],'meta':{'result_count':1}}
    def transport(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/rules'):return httpx.Response(200,json=rules)
        return httpx.Response(200,json=payload)
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        hunter=Providers(settings,store,client)
        assert 'example' in await remote.watches()
        assert await hunter.request('watch')==payload
        assert 'example' in await remote.watches()
    assert calls==['/2/tweets/search/stream/rules','/open/twitter_watch']
    assert remote.ledger.summary()['used']==1
    await remote.close()


async def test_filtered_stream_does_not_search_timelines(setup):
    import time
    cfg,store,settings=setup;calls=[];now=time.time()
    row={'subscription_id':'sub_gap','generation':1,'generation_at':now-86400,'handle':'example'}
    ledger=Ledger(__import__('os').environ['IKUN_6551_LEDGER'])
    ledger.mark_gap(now-3600);ledger.close_gap(now,[row]);job=ledger.jobs('sub_gap')[0]
    def transport(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'success':True,'data':[]})
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    with pytest.raises(RemoteError,match='backfill_disabled'):
        await remote.tweets('example',job=job)
    with pytest.raises(RemoteError,match='backfill_disabled'):
        await remote.tweets('example',job=job)
    assert calls==[]
    await remote.close()
