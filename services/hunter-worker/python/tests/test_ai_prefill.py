"""Owner decision 2026-10-18: AI Chinese prefill for new discoveries; draft only, no rating."""
import json

from conftest import NOW, discover
from hunterradar import ai_prefill, gemini
from hunterradar.formal import FormalService


def test_prefill_stored_as_suggestion_only(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    assert dto['ai_suggestion'] is None
    monkeypatch.setenv('IKUN_AI_CONFIG', str(tmp_path / 'missing.json'))
    assert ai_prefill.run_pass(store, {}) == 0

    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'api_key': 'AIza' + 'x' * 35}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    monkeypatch.setattr(FormalService, 'page', lambda self, kind, query, now=None: {'items': [dto | {'profile_bio': 'AI audits on Solana. vaultstreet.fun'}], 'next_cursor': None})
    monkeypatch.setattr(gemini, 'generate_json', lambda prompt, **kw: {'name': 'SOL上的AI审计发射台', 'website': 'invented.io', 'description': '为 Solana 项目做 AI 审计。', 'notes': '关注代币', 'rating': 'S'})
    assert ai_prefill.run_pass(store, {}) == 1
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    s = current['ai_suggestion']
    assert s['name'] == 'SOL上的AI审计发射台' and s['website'] == '' and 'rating' not in s
    assert current['review_state'] == 'pending' and current['revision'] == dto['revision']
    assert ai_prefill.run_pass(store, {}) == 0  # not repeated


def test_failures_do_not_raise_and_are_retried_later(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'api_key': 'AIza' + 'x' * 35}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    monkeypatch.setattr(FormalService, 'page', lambda self, kind, query, now=None: {'items': [dto], 'next_cursor': None})
    def boom(prompt, **kw): raise gemini.AIUnavailable('ai_http_500')
    monkeypatch.setattr(gemini, 'generate_json', boom)
    failures = {}
    assert ai_prefill.run_pass(store, failures) == 0 and dto['discovery_id'] in failures


def test_website_kept_only_when_in_bio():
    out = ai_prefill.clean({'name': 'X', 'website': 'https://VaultStreet.fun/app'}, 'h', 'play at vaultstreet.fun')
    assert out['website'] == 'https://vaultstreet.fun'
    assert ai_prefill.clean({'name': 'X', 'website': 'fake.io'}, 'h', 'no links')['website'] == ''


def test_website_from_recent_tweet_links_skips_third_party():
    tweets = [{'text': 'Testnet live', 'links': ['https://pindar.finance/app', 'https://x.com/i/article/1', 'https://t.me/pindar']}]
    domains = ai_prefill.link_domains(tweets)
    assert domains == ['pindar.finance']
    assert ai_prefill.clean({'name': 'P', 'website': 'pindar.finance'}, 'h', '', domains)['website'] == 'https://pindar.finance'
    assert ai_prefill.recent_tweets(None, 'h') == []


def test_site_reader_text_and_doc_links(monkeypatch):
    from hunterradar import site_reader
    raw = '<html><head><title>Pindar</title><meta name="description" content="Funding rate markets"></head><body><script>x()</script><a href="/docs/intro">Docs</a><a href="https://x.com/p">x</a><p>Fixed and floating legs.</p></body></html>'
    assert site_reader._text(raw).startswith('Pindar | Funding rate markets')
    assert 'x()' not in site_reader._text(raw)
    assert site_reader.doc_links('https://pindar.finance/', raw, ['https://pindar.gitbook.io/docs']) == ['https://pindar.gitbook.io/docs', 'https://pindar.finance/docs/intro']
    assert site_reader.bio_domains('Play at VaultStreet.fun and @someone.eth') == ['vaultstreet.fun']
    monkeypatch.setattr(site_reader, 'public_host', lambda host, proxy=None: False)
    assert site_reader.fetch('http://127.0.0.1/', None) == (None, '')


def test_codex_provider_runs_cli_and_parses_json(monkeypatch, tmp_path):
    import subprocess
    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'provider': 'codex', 'codex_bin': '/bin/true'}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    assert gemini.enabled() and gemini.settings()['provider'] == 'codex'
    seen = {}
    def fake_run(args, cwd, env, **kw):
        seen['args'] = args
        out = args[args.index('-o') + 1]
        open(out, 'w').write('```json\n{"name": "测试", "website": "", "description": "简介", "notes": ""}\n```')
        return subprocess.CompletedProcess(args, 0, b'', b'')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    value = gemini.generate_json('prompt')
    assert value['name'] == '测试' and seen['args'][1] == 'exec' and '--sandbox' in seen['args']
    monkeypatch.setattr(subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 1, b'', b'You have hit your usage limit'))
    import pytest
    with pytest.raises(gemini.AIUnavailable) as e: gemini.generate_json('p')
    assert str(e.value) == 'ai_rate_limited'


def test_profile_website_from_twitterapi_entities(monkeypatch):
    import httpx
    class S: token_twitterapi = 'k'; external_io_enabled = True
    payload = {'data': {'entities': {'url': {'urls': [{'expanded_url': 'https://www.conso.xyz/'}]}}}}
    class R:
        status_code = 200
        def json(self): return payload
    class C:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **kw): return R()
    monkeypatch.setattr(httpx, 'Client', C)
    assert ai_prefill.profile_website(S(), 'conso_xyz') == 'conso.xyz'
    payload['data']['entities']['url']['urls'][0]['expanded_url'] = 'https://linktr.ee/x'
    assert ai_prefill.profile_website(S(), 'x') is None
    assert ai_prefill.profile_website(None, 'x') is None


def test_watch_error_since_tracks_start_and_clears(store):
    store.set_state('watch_error', 'TimeoutError')
    first = store.states()['watch_error_since']
    store.set_state('watch_error', 'TimeoutError')
    assert store.states()['watch_error_since'] == first
    store.set_state('watch_error', None)
    assert 'watch_error_since' not in store.states()
