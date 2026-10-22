import sys
from pathlib import Path
root=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(root/'services/tracking-worker/python'),str(root/'services/hunter-worker/python')]
import httpx
import pytest
from tracking.config import Config
from tracking.remote import Remote, RemoteError
from hunterradar.config import Settings
from hunterradar.providers import Providers, ProviderError
from hunterradar.store import Store
from hunterradar.ai_prefill import recent_tweets
from provider_6551 import Ledger


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('IKUN_6551_LEDGER',str(tmp_path/'ops/ledger.db'))
    monkeypatch.setenv('IKUN_TRACKING_6551_TOKEN','PRIVATE_TOKEN')
    cfg=Config(db_path=tmp_path/'tracking/tracking.db',remote_enabled=True,dedicated_account=True,request_interval=0)
    store=Store(tmp_path/'hunter/hunter.db',initialize=True)
    settings=Settings(db=store.path,external_io_enabled=True,token_6551='PRIVATE_TOKEN')
    return cfg,store,settings


async def test_tracking_402_closes_hunter_and_ai_before_transport(setup):
    cfg,store,settings=setup;calls=[]
    def transport(request):calls.append(request.url.path);return httpx.Response(402,json={'success':False,'error':'insufficient quota'})
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        hunter=Providers(settings,store,client)
        with pytest.raises(RemoteError,match='quota_exhausted'):await remote.watches()
        for operation in ('watch','profile'):
            with pytest.raises(ProviderError,match='quota_exhausted'):await hunter.request(operation,'example')
        assert recent_tweets(settings,'example')==[]
        assert calls==['/open/twitter_watch']
    await remote.close()


async def test_watch_snapshot_is_one_shared_event_request(setup):
    cfg,store,settings=setup;calls=[]
    payload={'success':True,'data':[{'twAccount':'example','newTweetBol':True}]}
    def transport(request):calls.append(request.url.path);return httpx.Response(200,json=payload)
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        hunter=Providers(settings,store,client)
        assert 'example' in await remote.watches()
        assert await hunter.request('watch')==payload
        assert 'example' in await remote.watches()
    assert calls==['/open/twitter_watch']
    assert remote.ledger.summary()['used']==1
    await remote.close()


async def test_gap_search_uses_date_bounds_once_without_paid_replay(setup):
    import json,time
    cfg,store,settings=setup;calls=[];now=time.time()
    row={'subscription_id':'sub_gap','generation':1,'generation_at':now-86400,'handle':'example'}
    ledger=Ledger(__import__('os').environ['IKUN_6551_LEDGER'])
    ledger.mark_gap(now-3600);ledger.close_gap(now,[row]);job=ledger.jobs('sub_gap')[0]
    def transport(request):
        calls.append((request.url.path,json.loads(request.content)))
        return httpx.Response(200,json={'success':True,'data':[]})
    remote=Remote(cfg,transport=httpx.MockTransport(transport))
    assert await remote.tweets('example',job=job)==[]
    with pytest.raises(RemoteError,match='recovery_already_attempted'):
        await remote.tweets('example',job=job)
    assert len(calls)==1 and calls[0][0]=='/open/twitter_search'
    assert calls[0][1]['fromUser']=='example' and calls[0][1]['maxResults']==100
    assert 'sinceDate' in calls[0][1] and 'untilDate' in calls[0][1]
    await remote.close()
