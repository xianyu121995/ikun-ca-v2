import hashlib
import httpx
import pytest
from hunterradar.config import Settings
from hunterradar.providers import Providers,ProviderError
from hunterradar.parsers import followings
from conftest import ready,NOW

async def test_paid_result_survives_restart_and_is_consumed_with_baseline(store):
    row=ready(store,'hunter1',followers=1000)
    calls=[]
    async def response(request):
        calls.append(request)
        assert request.extensions['timeout']['read']==60
        return httpx.Response(200,json={'followings':[{'id':'991','userName':'target1'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        cfg=Settings(db=store.path,token_twitterapi='key',external_io_enabled=True)
        await Providers(cfg,store,client).request('followings','hunter1')
        payload=await Providers(cfg,store,client).request('followings','hunter1')
        assert len(calls)==1
        assert store.apply_poll(row,followings(payload),NOW)['baseline']
        key='provider_result:followings:'+hashlib.sha256(b'hunter1').hexdigest()
        assert key not in store.states()
        assert store.hunter(row['id'])['next_poll_at']==NOW+3600
        assert store.status()['daily_reserved']['twitterapi']==60

async def test_ambiguous_timeout_never_repeats_network_or_budget(store):
    calls=[]
    async def response(request):
        calls.append(request)
        raise httpx.ReadTimeout('contains sensitive transport details',request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        cfg=Settings(db=store.path,token_twitterapi='key',external_io_enabled=True)
        for _ in range(2):
            with pytest.raises(ProviderError,match='^provider_billing_unknown$'):
                await Providers(cfg,store,client).request('followings','hunter1')
    assert len(calls)==1
    assert store.status()['daily_reserved']['twitterapi']==60
    diagnostic=store.states()['provider_failure:followings:'+hashlib.sha256(b'hunter1').hexdigest()]
    assert diagnostic['kind']=='ReadTimeout' and 'sensitive' not in str(diagnostic)
