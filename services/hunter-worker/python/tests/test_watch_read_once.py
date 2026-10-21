import hashlib
import httpx
import pytest

from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.providers import Providers
from hunterradar.watch import recover_read_once
from conftest import ready

INTENT = 'provider_intent:watch:' + hashlib.sha256(b'').hexdigest()
FAILURE = 'provider_failure:watch:' + hashlib.sha256(b'').hexdigest()


async def test_only_watch_read_has_longer_timeout(store):
    seen = []
    def response(request):
        seen.append(request)
        return httpx.Response(200, json={'success': True, 'data': []})
    async with httpx.AsyncClient(timeout=10, transport=httpx.MockTransport(response)) as client:
        provider = Providers(Settings(db=store.path, token_6551='test', external_io_enabled=True), store, client)
        await provider.request('watch')
        await provider.request('profile', 'hunter1')
    assert seen[0].extensions['timeout'] == {'read': 20, 'connect': 10, 'write': 10, 'pool': 10}
    assert seen[1].extensions['timeout']['read'] == 10


@pytest.mark.parametrize('outcome', ['success', 'timeout', 'incomplete', 'missing', 'invalid_json'])
async def test_one_read_no_watch_writes_and_durable_protection(store, outcome):
    hunter = ready(store)
    store.set_state(INTENT, 'billing_unknown')
    prior_failure = {'kind': 'ReadTimeout', 'at': 123}
    store.set_state(FAILURE, prior_failure)
    store.set_state('watch_error', 'provider_billing_unknown')
    since = store.states()['watch_error_since']
    calls = []
    def response(request):
        calls.append(request)
        assert request.url.path == '/open/twitter_watch'
        assert request.extensions['timeout']['read'] == 20
        if outcome == 'timeout':
            raise httpx.ReadTimeout('secret detail', request=request)
        if outcome == 'invalid_json':
            return httpx.Response(200, text='not json')
        data = [{'twAccount': hunter['username'], 'newFlwBol': outcome != 'missing'}]
        if outcome == 'incomplete':
            data = {'list': data, 'total': 2}
        return httpx.Response(200, json={'success': True, 'data': data})
    owner = store.acquire_worker()
    view = store.worker_view(owner)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            cfg = Settings(db=store.path, token_6551='test', external_io_enabled=True)
            provider = Providers(cfg, view, client)
            result = await recover_read_once(view, provider, 'approved-once')
            assert await recover_read_once(view, provider, 'approved-once') == result
            assert len(calls) == 1
            assert view.status()['daily_reserved']['6551'] == 1
            assert result['previous_failure'] == prior_failure
            # Resume loop once: neither success nor failure may make another immediate request.
            engine = Engine(cfg, view, provider)
            async def stop_after_one(_):
                engine.stop.set()
            engine.pause = stop_after_one
            await engine.watch_loop()
            assert len(calls) == 1
        states = view.states()
        if outcome == 'success':
            assert result['status'] == 'succeeded' and result['covered'] == 1
            assert states['watch_error'] is None and states[INTENT] is None
            assert 'watch_error_since' not in states
            assert view.hunter(hunter['id'])['watch_covered'] == 1
            assert states[FAILURE] == prior_failure
        else:
            assert result['status'] == 'failed'
            assert states[INTENT] == 'billing_unknown'
            assert states['watch_error'] == 'provider_billing_unknown'
            assert states['watch_error_since'] == since
            assert 'secret' not in str(result)
    finally:
        store.release_worker(owner)


async def test_crashed_operator_receipt_cannot_retry_on_restart(store):
    ready(store)
    store.set_state('watch_read_once', {'approval': 'crashed', 'status': 'started'})
    calls = []
    def response(request):
        calls.append(request)
        return httpx.Response(200, json={'data': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        cfg = Settings(db=store.path, token_6551='test', external_io_enabled=True)
        engine = Engine(cfg, store, Providers(cfg, store, client))
        async def stop_after_one(_):
            engine.stop.set()
        engine.pause = stop_after_one
        await engine.watch_loop()
    assert not calls
    assert store.states()['watch_error'] == 'provider_billing_unknown'
