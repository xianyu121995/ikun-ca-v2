"""Hot paths must not parse the whole state table; expired enrichment caches are pruned safely."""
import hashlib
import json

import httpx
import pytest

from conftest import NOW, ready
from hunterradar.config import Settings
from hunterradar.providers import Providers
from hunterradar.rest_batches import claim, KEY
from hunterradar.store import Store, LEGACY_DIRECTORY_PREFIX

START = int(NOW//3600)*3600


def put(store, key, value):
    with store.connect(True) as db:
        db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (key, json.dumps(value)))


def raw_keys(store):
    with store.connect() as db:
        return {r[0] for r in db.execute('SELECT key FROM state')}


def forbid_full_read(monkeypatch):
    def boom(self):
        raise AssertionError('full_state_table_read_on_hot_path')
    monkeypatch.setattr(Store, 'states', boom)


def test_targeted_state_reads(store):
    put(store, 'a:1', {'x': 1})
    put(store, 'a:2', [2])
    put(store, 'b:1', None)
    put(store, LEGACY_DIRECTORY_PREFIX+'account:z', {'secret': True})
    assert store.get_state('a:1') == {'x': 1}
    assert store.get_state('missing', 7) == 7
    assert store.get_state(LEGACY_DIRECTORY_PREFIX+'account:z') is None
    assert store.get_states(['a:1', 'b:1', 'missing', LEGACY_DIRECTORY_PREFIX+'account:z']) == {'a:1': {'x': 1}, 'b:1': None}
    assert store.list_states('a:') == {'a:1': {'x': 1}, 'a:2': [2]}
    with pytest.raises(ValueError):
        store.list_states(LEGACY_DIRECTORY_PREFIX)


def test_status_and_claim_do_not_parse_whole_table(store, monkeypatch):
    for i in range(24):
        ready(store, 'h'+str(i), followers=100, user_id=str(1000+i))
    forbid_full_read(monkeypatch)
    assert store.status()['worker_alive'] is False
    assert len(claim(store, START+2)) == 2
    assert store.get_state(KEY)['last_slot'] == int((START+2)//300)


async def test_provider_request_reads_only_needed_rows(store, monkeypatch):
    forbid_full_read(monkeypatch)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'status': 'success', 'data': {'tweets': []}})
    cfg = Settings(db=store.path, rest_only=True, external_io_enabled=True, token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = Providers(cfg, store, client)
        await p.request('tweets', 'h')
        await p.request('tweets', 'h')  # served from the one-hour cache
    assert len(calls) == 1


def test_prune_only_expired_enrichment_caches(store):
    h = hashlib.sha256(b'h').hexdigest()
    old, fresh = NOW-3601, NOW-60
    protected = {
        'provider_intent:tweets:'+h: 'billing_unknown',
        'provider_intent:ai_profile:'+h: 'in_flight',
        'provider_intent:blocked:twitterapi:tweets:'+h: {'state': 'blocked', 'code': 'provider_http_404'},
        'provider_result:followings:'+h: {'payload': {}, 'received_at': old, 'generation': None},
        'provider_result:profile:'+h: {'payload': {}, 'received_at': old, 'generation': None},
        'cooldown:twitterapi': old,
        'ai:discovery-1': {'name': 'x', 'generated_at': old},
        'provider_result:tweets:fresh': {'payload': {}, 'received_at': fresh},
        'provider_result:tweets:weird': {'payload': {}, 'received_at': 'not-a-number'},
        'provider_result:tweets:list': ['unexpected'],
        'ai_input:fresh': {'at': fresh, 'tweets': []},
    }
    expired = {
        'provider_result:tweets:'+h: {'payload': {'big': 'x'*1000}, 'received_at': old},
        'provider_result:ai_profile:'+h: {'payload': {}, 'received_at': old},
        'ai_input:h': {'at': old, 'tweets': [{'text': 't'}]},
    }
    for key, value in {**protected, **expired}.items():
        put(store, key, value)
    assert store.prune_expired_caches(NOW) == 3
    keys = raw_keys(store)
    assert set(protected) <= keys
    assert not set(expired) & keys
    assert store.prune_expired_caches(NOW) == 0


def test_prune_refuses_window_shorter_than_reuse(store):
    with pytest.raises(ValueError):
        store.prune_expired_caches(NOW, max_age=60)


def test_prune_respects_limit(store):
    for i in range(5):
        put(store, f'ai_input:h{i}', {'at': NOW-7200, 'tweets': []})
    assert store.prune_expired_caches(NOW, limit=2) == 2
    assert store.prune_expired_caches(NOW) == 3
