import asyncio
from collections import Counter
import hashlib

import httpx
import pytest

from conftest import NOW, ready, event
from hunterradar import ai_prefill
from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.parsers import Target
from hunterradar.providers import Providers, ProviderError
from hunterradar.rest_batches import claim, KEY
from hunterradar.retention import backup_bundle, micros, restore_bundle
from hunterradar.store import Store, Conflict

START = int(NOW//3600)*3600


def cohort(store, count=85):
    return [ready(store, 'h'+str(i), followers=100, user_id=str(1000+i)) for i in range(count)]


def test_85_hourly_cohorts_survive_restart_without_completion_drift(store):
    rows = cohort(store)
    counts = Counter()
    groups = None
    for slot in range(36):
        now = START+slot*300+2  # Actual wakeups are never exactly on the boundary.
        reopened = Store(store.path)
        batch = claim(reopened, now)
        assert len(batch) == (8 if slot%12==11 else 7)
        current = reopened.states()[KEY]['groups']
        assert groups is None or groups == current
        groups = current
        assert claim(Store(store.path), now+1) == []
        for row in batch:
            counts[row['id']] += 1
            # Slow completions must not turn hourly polling into every TWO hours.
            reopened.apply_poll(row, [], now+40, next_poll_at=row['batch_next_poll_at'])
    assert counts == Counter({r['id']:3 for r in rows})


def test_restart_skips_missed_slots_and_never_replays_crash_claim(store):
    cohort(store)
    first = claim(store, START)
    assert len(first)==7
    assert len(claim(Store(store.path),START+4*300))==7
    assert claim(Store(store.path),START+4*300)==[]
    # Backward wall clock adjustments must not re-open earlier slots.
    assert claim(Store(store.path),START+1)==[]
    assert len(claim(Store(store.path),START+5*300))==7


def test_member_due_later_inside_current_slot_is_dispatched_once(store):
    cohort(store)
    claim(store,START)
    identifier=store.states()[KEY]['groups'][5][0]
    with store.connect(True) as db:
        db.execute('UPDATE hunters SET next_poll_at=? WHERE id=?',(START+5*300+20,identifier))
    first=claim(store,START+5*300)
    assert len(first)==6 and identifier not in {r['id'] for r in first}
    assert claim(Store(store.path),START+5*300+19)==[]
    later=claim(Store(store.path),START+5*300+20)
    assert [r['id'] for r in later]==[identifier]
    assert claim(Store(store.path),START+5*300+21)==[]


def test_edits_balance_membership_and_disabled_accounts_never_dispatch(store):
    rows=cohort(store)
    claim(store,START)
    before=store.states()[KEY]['groups']
    removed=store.hunter(rows[0]['id'])
    store.patch(removed['id'],removed['version'],enabled=False)
    added=ready(store,'new_h',followers=100,user_id='9000')
    claim(store,START+300)
    after=store.states()[KEY]['groups']
    members={k for group in after for k in group}
    assert removed['id'] not in members and added['id'] in members and len(members)==85
    assert max(map(len,after))-min(map(len,after))==1
    assert sum(a!=b for a,b in zip(before,after))<=2


def test_backoff_and_terminal_fences_skip_only_affected_accounts(store):
    cohort(store,24)
    batch=claim(store,START)
    blocked=batch[0]
    intent='provider_intent:followings:'+hashlib.sha256(blocked['username'].encode()).hexdigest()
    store.set_state(intent,'billing_unknown')
    store.job_failure(blocked,'poll','provider_billing_unknown',9999999999)
    retry=batch[1]
    store.job_failure(retry,'poll','provider_rate_limited',START+2*3600)
    assert claim(store,START+3600)==[]
    other=claim(store,START+3600+300)
    assert len(other)==2 and all(r['id'] not in {blocked['id'],retry['id']} for r in other)
    assert store.states()[intent]=='billing_unknown'


def test_wss_cutover_seeds_new_generation_and_preserves_history(store):
    row=ready(store)
    store.ingest_wss(event())
    with store.connect() as db:
        history=db.execute('SELECT count(*) FROM follow_events').fetchone()[0]
    targets=[Target('old_follow','9999','Old','')]
    result=store.apply_rest_cutover(row,targets,NOW)
    current=store.hunter(row['id'])
    assert result['baseline'] and result['new']==0 and result['migrated']
    assert current['id']==row['id'] and current['mode']=='REST'
    assert current['generation']==row['generation']+1 and current['baseline_ready']
    assert store.states()['rest_cutover:'+row['id']]['watch_cleanup']=='pending'
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM follow_events').fetchone()[0]==history
    assert store.apply_rest_cutover(row,targets,NOW)['discarded']
    assert store.apply_poll(current,targets+[Target('new_follow','9998','New','')],NOW+3600)['new']==1


def test_cutover_identity_failure_rolls_back_mode_generation_and_marker(store):
    row=ready(store)
    with pytest.raises(Conflict):
        store.apply_rest_cutover(row,[Target('same','90','',''),Target('same','91','','')],NOW)
    assert store.hunter(row['id'])==row
    assert 'rest_cutover:'+row['id'] not in store.states()
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM seen_targets').fetchone()[0]==0


async def test_paid_wss_result_replayed_locally_after_crash_without_second_request(store):
    row=ready(store)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'followings':[{'userName':'existing','id':'990'}]})
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p=Providers(cfg,store,client)
        await p.request('followings',row['username'])
        engine=Engine(cfg,Store(store.path),p)
        engine.replay_rest_results()
        engine.replay_rest_results()
    assert len(calls)==1 and store.hunter(row['id'])['mode']=='REST'
    assert store.status()['events']==0 and store.status()['daily_reserved']['twitterapi']==60


def test_crash_replay_keeps_original_cohort_due_time(store,monkeypatch):
    cohort(store)
    dispatched=claim(store,START)
    row=dispatched[0]
    key='provider_result:followings:'+hashlib.sha256(row['username'].encode()).hexdigest()
    store.set_state(key,{'payload':{'followings':[]},'received_at':START+10,'generation':[row['id'],row['generation']]})
    monkeypatch.setattr('hunterradar.engine.time.time',lambda:START+2*300+1)
    Engine(Settings(db=store.path,rest_only=True),store,providers=object()).replay_rest_results()
    assert store.hunter(row['id'])['next_poll_at']==START+3600
    assert row['id'] in {r['id'] for r in claim(Store(store.path),START+3600+1)}


async def test_new_high_follower_hunter_uses_twi_and_stays_rest(store,monkeypatch):
    monkeypatch.setenv('IKUN_6551_REST_PAUSED','1')
    row=store.add('new_hunter')
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.host=='api.twitterapi.io' and request.url.path=='/twitter/user/info'
        return httpx.Response(200,json={'data':{'id':'100','userName':'new_hunter','followers':99999}})
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await Engine(cfg,store,Providers(cfg,store,client)).scan_profile(row)
    assert len(calls)==1 and store.hunter(row['id'])['mode']=='REST'
    assert store.status()['daily_reserved']=={'twitterapi':18}


async def test_profile_paid_response_survives_crash_until_atomic_profile_commit(store):
    row=store.add('new_hunter')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'data':{'id':'100','userName':'new_hunter','followers':99999}})
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await Providers(cfg,store,client).request('profile','new_hunter')
        reopened=Store(store.path)
        await Engine(cfg,reopened,Providers(cfg,reopened,client)).scan_profile(row)
    assert len(calls)==1 and store.hunter(row['id'])['profile_status']=='ready'
    assert store.status()['daily_reserved']=={'twitterapi':18}
    assert not any(k.startswith('provider_result:profile:') for k in store.states())


async def test_rest_only_closes_hunter_watch_and_wss_even_if_invoked_directly(store):
    ready(store)
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_6551='fixture')
    def forbidden(*args,**kwargs):raise AssertionError('6551 transport must remain closed')
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        provider=Providers(cfg,store,client)
        engine=Engine(cfg,store,provider,connector=forbidden)
        for fn in (lambda:provider.request('watch'), lambda:provider.watch_write('twitter_watch_add',{}),engine.consume):
            with pytest.raises(ProviderError,match='hunter_rest_only'):await fn()
        tasks=[asyncio.create_task(engine.watch_loop()),asyncio.create_task(engine.wss_loop())]
        await asyncio.sleep(0)
        assert not any(t.done() for t in tasks)
        engine.stop.set()
        await asyncio.wait_for(asyncio.gather(*tasks),1)
    assert store.status()['daily_reserved']=={}


@pytest.mark.parametrize('operation,cost',[('profile',18),('ai_profile',18),('tweets',300)])
async def test_all_twi_inputs_share_budget_and_ambiguous_billing_fence(store,operation,cost):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('sensitive transport',request=request)
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p=Providers(cfg,store,client)
        for _ in range(2):
            with pytest.raises(ProviderError,match='provider_billing_unknown'):await p.request(operation,'h')
    assert len(calls)==1 and store.status()['daily_reserved']['twitterapi']==cost


async def test_twi_profile_402_blocks_all_twi_following_and_ai_calls(store):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(402)
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p=Providers(cfg,store,client)
        for op in ('profile','followings','tweets','ai_profile'):
            with pytest.raises(ProviderError,match='provider_http_402'):await p.request(op,'h')
    assert len(calls)==1


def test_ai_inputs_use_twi_budget_and_ignore_6551_quota(store,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.host=='api.twitterapi.io'
        if request.url.path.endswith('last_tweets'):
            return httpx.Response(200,json={'status':'success','data':{'tweets':[{'text':'Fixture','entities':{'urls':[{'expanded_url':'https://fixture.example/'}]}}]}})
        return httpx.Response(200,json={'data':{'entities':{'url':{'urls':[{'expanded_url':'https://fixture.example/'}]}}}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('IKUN_6551_REST_PAUSED','1')
    cfg=Settings(db=store.path,rest_only=True,external_io_enabled=True,token_twitterapi='fixture')
    assert ai_prefill.recent_tweets(cfg,'h',store=store)==[{'text':'Fixture','links':['https://fixture.example/']}]
    assert ai_prefill.profile_website(cfg,'h',store=store)=='fixture.example'
    assert ai_prefill.recent_tweets(cfg,'h',store=store)[0]['text']=='Fixture'
    assert ai_prefill.profile_website(cfg,'h',store=store)=='fixture.example'
    assert len(calls)==2
    assert store.status()['daily_reserved']=={'twitterapi':318}
    monkeypatch.setattr(ai_prefill,'configured',lambda: (_ for _ in ()).throw(AssertionError('6551 quota is irrelevant')))
    monkeypatch.setattr(ai_prefill.gemini,'enabled',lambda:False)
    assert ai_prefill.run_pass(store,{},settings=cfg)==0


def test_load_explicit_rest_policy_and_daily_budget(monkeypatch):
    monkeypatch.setenv('HUNTER_REST_ONLY','1')
    monkeypatch.setenv('HUNTER_TWITTERAPI_DAILY_CREDITS','150000')
    cfg=Settings.load()
    assert cfg.rest_only and cfg.daily_twitterapi==150000


@pytest.mark.parametrize('change',['claim','cutover','poll','paid_result'])
def test_restore_rejects_incoherent_old_rest_checkpoint(store,tmp_path,change):
    row=ready(store,followers=100 if change!='cutover' else 5000)
    claim(store,START)
    bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW))
    if change=='claim':claim(store,START+300)
    elif change=='cutover':store.apply_rest_cutover(row,[],NOW)
    elif change=='poll':store.apply_poll(row,[Target('new_seen','989','','')],NOW)
    else:store.set_state('provider_result:followings:fixture',{'received_at':NOW})
    destination=tmp_path.resolve()/'restored'/'hunter.db'
    with pytest.raises(ValueError,match='restore_rest_(checkpoint|baseline)_mismatch'):
        restore_bundle(bundle,destination,current=store.path)
    assert not destination.exists()


def test_coherent_rest_backup_restores_all_batch_and_baseline_state(store,tmp_path):
    row=ready(store)
    claim(store,START)
    store.apply_rest_cutover(row,[Target('existing','787','','')],NOW)
    bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW))
    destination=tmp_path.resolve()/'restored'/'hunter.db'
    restore_bundle(bundle,destination,current=store.path)
    restored=Store(destination)
    assert restored.states()[KEY]==store.states()[KEY]
    assert restored.hunter(row['id'])==store.hunter(row['id'])


def test_disabled_wss_source_never_projects_stale_pong_as_connected(store):
    from hunterradar.formal import account_dto
    row=ready(store)
    store.coverage([row['username']],NOW)
    store.set_state('last_pong_at',NOW)
    store.set_state('worker_heartbeat',NOW)
    store.set_state('wss_state','disabled_rest_only')
    with store.connect() as db:
        dto=account_dto(db,store.hunter(row['id']),NOW)
    assert dto['connection']=='disconnected'
