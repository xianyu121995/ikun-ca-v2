import httpx
import pytest
from hunterradar.config import Settings
from hunterradar.providers import Providers, ProviderError
from hunterradar.ai_prefill import recent_tweets


async def test_pause_fences_all_6551_routes_before_transport(store,monkeypatch):
    monkeypatch.setenv('IKUN_6551_REST_PAUSED','1')
    settings=Settings(db=store.path,external_io_enabled=True,token_6551='fixture')
    def forbidden(request):raise AssertionError('provider transport must stay closed')
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        provider=Providers(settings,store,client)
        for operation in ('profile','watch'):
            with pytest.raises(ProviderError,match='quota_exhausted'):
                await provider.request(operation,'example')
        with pytest.raises(ProviderError,match='quota_exhausted'):
            await provider.watch_write('twitter_watch_add',{})
    assert recent_tweets(settings,'example')==[]
