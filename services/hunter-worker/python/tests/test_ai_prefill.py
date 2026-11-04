"""AI prefill: text fields stay a draft; S/A/B/忽略 is written immediately."""
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
    monkeypatch.setattr(gemini, 'generate_json', lambda prompt, **kw: {'name': 'SOL上的AI审计发射台', 'website': 'invented.io', 'description': '为 Solana 项目做 AI 审计。', 'notes': '关注代币', 'rating': 'S', 'rating_reason': '官网和推文都写了正在做的审计产品。'})
    assert '忽略' in ai_prefill.PROMPT and 'rating_reason' in ai_prefill.PROMPT
    assert ai_prefill.run_pass(store, {}) == 1
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    s = current['ai_suggestion']
    assert s['name'] == 'SOL上的AI审计发射台' and s['website'] == '' and s['rating'] == 'S'
    assert s['rating_reason'] == '官网和推文都写了正在做的审计产品。'
    assert current['project']['rating'] == 'S' and current['review_state'] == 'pending'
    assert '融资' not in ai_prefill.PROMPT and '团队' not in ai_prefill.PROMPT
    assert ai_prefill.RATING_RUBRIC in ai_prefill.PROMPT
    assert '同生态' not in ai_prefill.RATING_RUBRIC and '不是忽略理由' in ai_prefill.RATING_RUBRIC
    with store.connect() as db:
        stored = db.execute('SELECT ignored,rating_reason FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert stored['ignored'] == 0 and stored['rating_reason'] == '官网和推文都写了正在做的审计产品。'
    assert current['revision'] == dto['revision'] + 1
    assert ai_prefill.run_pass(store, {}) == 0  # not repeated


def test_ai_ignore_stays_in_the_default_list(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'api_key': 'AIza' + 'x' * 35}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    real_page = FormalService.page
    monkeypatch.setattr(FormalService, 'page', lambda self, kind, query, now=None: {'items': [dto | {'profile_bio': 'airdrop spam'}], 'next_cursor': None})
    monkeypatch.setattr(gemini, 'generate_json', lambda prompt, **kw: {'name': '喊单', 'website': '', 'description': '没有产品', 'notes': '', 'rating': '忽略', 'rating_reason': '只有喊单，看不出项目。'})
    assert ai_prefill.run_pass(store, {}) == 1
    monkeypatch.setattr(FormalService, 'page', real_page)
    listed = FormalService(store).page('signals', {'limit': '100'}, NOW)['items']
    assert dto['discovery_id'] in [item['discovery_id'] for item in listed]
    hidden = FormalService(store).page('signals', {'limit': '100', 'review_state': 'ignored'}, NOW)['items']
    assert hidden == []
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert current['review_state'] == 'pending' and current['project']['rating'] is None
    assert current['ai_suggestion']['rating'] == '忽略'
    assert current['ai_suggestion']['rating_reason'] == '只有喊单，看不出项目。'
    with store.connect() as db:
        row = db.execute('SELECT ignored,rating,rating_reason,rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert row['ignored'] == 0 and row['rating'] == '忽略' and row['rating_reason'] == '只有喊单，看不出项目。' and row['rating_source'] == 'ai'
    assert current['rating_source'] == 'ai'


def test_existing_human_rating_is_not_replaced(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET rating='A' WHERE discovery_id=?", (dto['discovery_id'],))
    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'provider': 'codex', 'api_key': 'AIza' + 'x' * 35}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    monkeypatch.setattr(FormalService, 'page', lambda self, kind, query, now=None: {'items': [dto | {'profile_bio': 'built a protocol'}], 'next_cursor': None})
    monkeypatch.setattr(gemini, 'generate_json', lambda prompt, **kw: {'name': '新名', 'website': '', 'description': '简介', 'notes': '', 'rating': '忽略', 'rating_reason': '不该覆盖人工评级。'})
    assert ai_prefill.run_pass(store, {}) == 1
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert current['project']['rating'] == 'A' and current['review_state'] == 'pending'
    assert current['ai_suggestion']['rating'] == '忽略'


def test_rating_without_a_reason_is_not_applied(store, monkeypatch, tmp_path):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    cfg = tmp_path / 'ai.json'; cfg.write_text(json.dumps({'enabled': True, 'provider': 'deepseek', 'api_key': 'sk-' + 'd' * 32}))
    monkeypatch.setenv('IKUN_AI_CONFIG', str(cfg))
    monkeypatch.setattr(FormalService, 'page', lambda self, kind, query, now=None: {'items': [dto], 'next_cursor': None})
    monkeypatch.setattr(gemini, 'generate_json', lambda prompt, **kw: {'name': '未评级', 'website': '', 'description': '简介', 'notes': '', 'rating': 'C'})
    assert ai_prefill.run_pass(store, {}) == 1
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert current['project']['rating'] is None and current['review_state'] == 'pending'
    assert 'rating' not in current['ai_suggestion']


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


def test_clean_keeps_a_known_rating_only_with_a_reason():
    assert 'rating' not in ai_prefill.clean({'rating': '忽略'}, 'h', '')
    out = ai_prefill.clean({'rating': '忽略', 'rating_reason': '  广告号  '}, 'h', '')
    assert out['rating'] == '忽略' and out['rating_reason'] == '广告号'
    assert len(ai_prefill.clean({'rating': 'B', 'rating_reason': '理' * 50}, 'h', '')['rating_reason']) == 40
    assert 'rating' not in ai_prefill.clean({'rating': 'C', 'rating_reason': '不是等级'}, 'h', '')
    assert '纯 PFP' in ai_prefill.RATING_RUBRIC and '未来才开始也不是忽略' in ai_prefill.RATING_RUBRIC


def test_prompt_input_passes_signal_count_and_known_followers_only():
    item = {'x_handle': 'h', 'project': {'name': 'N'}, 'signal_count': 4, 'followers': None}
    site = {'site': '', 'docs': ''}
    payload = ai_prefill.prompt_input(item, 'bio', [], [], site)
    assert payload['signal_count'] == 4 and 'followers_count' not in payload
    item['followers'] = 15000
    assert ai_prefill.prompt_input(item, 'bio', [], [], site)['followers_count'] == 15000
    item['followers'] = True
    item['followers_count'] = 9
    assert ai_prefill.prompt_input(item, 'bio', [], [], site)['followers_count'] == 9
    item['followers_count'] = None
    assert 'followers_count' not in ai_prefill.prompt_input(item, 'bio', [], [], site)


def test_apply_rating_writes_prefill_and_keeps_human_decisions(store):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    ai_prefill.apply_rating(store, dto, {'rating': '忽略', 'rating_reason': '  广告号  '})
    with store.connect() as db:
        row = db.execute('SELECT ignored,rating,rating_reason,rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert row['ignored'] == 0 and row['rating'] == '忽略' and row['rating_reason'] == '广告号' and row['rating_source'] == 'ai'
    listed = FormalService(store).page('signals', {'limit': '100'}, NOW)['items']
    assert dto['discovery_id'] in [item['discovery_id'] for item in listed]
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET name='已命名', rating='待定', rating_reason=NULL WHERE discovery_id=?", (dto['discovery_id'],))
    ai_prefill.apply_rating(store, dto, {'rating': 'S', 'rating_reason': '不该覆盖。'})
    with store.connect() as db:
        row = db.execute('SELECT rating,rating_reason,ignored FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert row['rating'] == '待定' and row['rating_reason'] is None and row['ignored'] == 0
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET name='', rating='A' WHERE discovery_id=?", (dto['discovery_id'],))
    ai_prefill.apply_rating(store, dto, {'rating': '忽略', 'rating_reason': '不该覆盖。'})
    with store.connect() as db:
        row = db.execute('SELECT rating,ignored FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert row['rating'] == 'A' and row['ignored'] == 0
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET rating='待定', ignored=1 WHERE discovery_id=?", (dto['discovery_id'],))
    ai_prefill.apply_rating(store, dto, {'rating': 'S', 'rating_reason': '不该打开。'})
    with store.connect() as db:
        row = db.execute('SELECT rating,ignored FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()
    assert row['ignored'] == 1 and row['rating'] == '待定'


def test_human_ignore_still_hides_until_a_person_picks_another_level(store):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    from hunterradar.protocol import Principal
    admin = Principal(user_id='fixture-admin', tenant_id='ikun-main', role='superadmin')
    path = '/api/v1/hunter/discoveries/' + dto['discovery_id']
    FormalService(store).write(admin, 'PATCH', path, {'ignored': True}, '22222222-2222-4222-8222-222222222222', f'"rev-{dto["revision"]}"', 'fixture-research', NOW)
    listed = FormalService(store).page('signals', {'limit': '100'}, NOW)['items']
    assert dto['discovery_id'] not in [item['discovery_id'] for item in listed]
    hidden = FormalService(store).page('signals', {'limit': '100', 'review_state': 'ignored'}, NOW)['items']
    current = hidden[0]
    FormalService(store).write(admin, 'PATCH', path, {'rating': 'B'}, '33333333-3333-4333-8333-333333333333', f'"rev-{current["revision"]}"', 'fixture-research', NOW)
    restored = FormalService(store).page('signals', {'limit': '100'}, NOW)['items']
    assert dto['discovery_id'] in [item['discovery_id'] for item in restored]
    saved = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert saved['project']['rating'] == 'B' and saved['rating_source'] == 'human'
    with store.connect() as db:
        assert db.execute('SELECT rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()[0] == 'human'


def test_rating_source_stays_ai_until_the_owner_sets_a_rating(store):
    dto = FormalService(store).discovery(discover(store)['discovery_id'], NOW)
    ai_prefill.apply_rating(store, dto, {'rating': 'S', 'rating_reason': '机制和入口都清楚。'})
    current = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert current['rating_source'] == 'ai' and current['project']['rating'] == 'S'
    assert current['rating_reason'] == '机制和入口都清楚。'
    from hunterradar.protocol import Principal
    admin = Principal(user_id='fixture-admin', tenant_id='ikun-main', role='superadmin')
    path = '/api/v1/hunter/discoveries/' + dto['discovery_id']
    FormalService(store).write(admin, 'PATCH', path, {'rating': 'A'}, '44444444-4444-4444-8444-444444444444', f'"rev-{current["revision"]}"', 'fixture-research', NOW)
    saved = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert saved['rating_source'] == 'human' and saved['project']['rating'] == 'A'
    ai_prefill.apply_rating(store, dto, {'rating': '忽略', 'rating_reason': '不该覆盖人工评级。'})
    again = FormalService(store).discovery(dto['discovery_id'], NOW)
    assert again['rating_source'] == 'human' and again['project']['rating'] == 'A' and again['review_state'] != 'ignored'
    from hunterradar.migration import ensure_rating_reason
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET rating='B', rating_source=NULL, rating_reason=NULL, name='', project_json=NULL, ignored=0 WHERE discovery_id=?", (dto['discovery_id'],))
    assert ensure_rating_reason(store.path) is False
    with store.connect() as db:
        assert db.execute('SELECT rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()[0] == 'human'
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET rating='S', rating_source=NULL, rating_reason='机制清楚。' WHERE discovery_id=?", (dto['discovery_id'],))
    ensure_rating_reason(store.path)
    with store.connect() as db:
        assert db.execute('SELECT rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()[0] == 'ai'
    with store.connect(True) as db:
        db.execute("UPDATE discoveries SET rating='待定', rating_source=NULL, rating_reason=NULL WHERE discovery_id=?", (dto['discovery_id'],))
    ensure_rating_reason(store.path)
    with store.connect() as db:
        assert db.execute('SELECT rating_source FROM discoveries WHERE discovery_id=?', (dto['discovery_id'],)).fetchone()[0] is None


def test_rating_reason_column_is_added_once(store):
    import sqlite3
    from hunterradar.migration import ensure_rating_reason
    assert ensure_rating_reason(store.path) is False
    with sqlite3.connect(store.path) as db:
        db.execute('ALTER TABLE discoveries DROP COLUMN rating_reason')
        db.execute('ALTER TABLE discoveries DROP COLUMN rating_source')
    assert ensure_rating_reason(store.path) is True
    assert ensure_rating_reason(store.path) is False
    with sqlite3.connect(store.path) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(discoveries)')]
    assert 'rating_reason' in columns and 'rating_source' in columns


def test_followings_follower_count_is_stored_without_a_new_request(store):
    from conftest import ready
    from hunterradar.parsers import Follow, Target, followings
    assert followings({'followings': [{'userName': 'Target', 'id': '123'}]})[0].followers is None
    assert followings({'followings': [{'userName': 'Target', 'id': '123', 'followers_count': 15000, 'followers': 1}]})[0].followers == 15000
    for index in (1, 2):
        ready(store, 'fh' + str(index), followers=5000, user_id=str(200 + index), now=NOW)
        store.ingest_wss(Follow('fh' + str(index), Target('counted', '1001', 'Counted', 'bio', 15000), NOW, NOW, '6551_WSS', 'counted-' + str(index)))
    found = FormalService(store).discovery(store.discovery('counted')['discovery_id'], NOW)
    assert found['followers'] == 15000
    dto = discover(store)
    assert FormalService(store).discovery(dto['discovery_id'], NOW)['followers'] is None
    ready(store, 'hunter3', followers=5000, user_id='103', now=NOW)
    store.ingest_wss(Follow('hunter3', Target('project1', '999', 'Project One', 'Evidence bio', 8000), NOW, NOW, '6551_WSS', 'later-count'))
    assert FormalService(store).discovery(dto['discovery_id'], NOW)['followers'] == 8000


def test_restore_script_clears_only_listed_rows_without_a_human_ignore(store):
    import importlib.util
    from conftest import event
    from pathlib import Path
    first = discover(store)
    store.ingest_wss(event('hunter1', 'project2', key='p2a', target_id='1002'))
    store.ingest_wss(event('hunter2', 'project2', key='p2b', target_id='1002'))
    second = store.discovery('project2')
    with store.connect(True) as db:
        db.execute('UPDATE discoveries SET ignored=1 WHERE discovery_id IN (?,?)', (first['discovery_id'], second['discovery_id']))
        store.audit(db, 'usr_owner', 'discovery.research.patch', first['discovery_id'], NOW, '{"fields":["ignored"]}')
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'restore_ai_ignored.py'
    spec = importlib.util.spec_from_file_location('restore_ai_ignored', path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    planned = script.run(store.path, ['project1', 'project2', 'missing'])
    by_input = {row['input']: row['action'] for row in planned}
    assert by_input == {'project1': 'skipped_human', 'project2': 'would_clear', 'missing': 'missing'}
    with store.connect() as db:
        assert db.execute('SELECT ignored FROM discoveries WHERE target=?', ('project2',)).fetchone()[0] == 1
    blocked = script.run(store.path, ['project2', 'missing'], apply=True)
    assert {row['action'] for row in blocked} == {'not_applied', 'missing'}
    with store.connect() as db:
        assert db.execute('SELECT ignored FROM discoveries WHERE target=?', ('project2',)).fetchone()[0] == 1
    applied = script.run(store.path, ['@project2'], apply=True)
    assert applied[0]['action'] == 'cleared' and applied[0]['rating'] == '待定'
    with store.connect() as db:
        row = db.execute('SELECT ignored,rating FROM discoveries WHERE target=?', ('project2',)).fetchone()
    assert row['ignored'] == 0 and row['rating'] == '待定'
    again = script.run(store.path, ['project2'], apply=True)
    assert again[0]['action'] == 'unchanged'
