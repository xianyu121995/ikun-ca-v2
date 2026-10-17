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
