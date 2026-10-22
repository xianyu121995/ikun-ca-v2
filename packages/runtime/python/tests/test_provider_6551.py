from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from provider_6551 import Ledger, Blocked, response_error, quota_response
import httpx


def test_shared_402_circuit_has_one_low_frequency_probe_and_survives_restart(tmp_path):
    now=[1792670000.0];path=tmp_path/'ops/ledger.sqlite3'
    first=Ledger(path,clock=lambda:now[0]);second=Ledger(path,clock=lambda:now[0])
    permit=first.begin('tracking','twitter_watch');first.finish(permit,402,quota=True)
    for ledger in (first,second,Ledger(path,clock=lambda:now[0])):
        with pytest.raises(Blocked,match='quota_exhausted'):ledger.begin('hunter_ai','twitter_user_tweets')
    assert second.summary()['used']==1
    now[0]+=3601
    permit=second.begin('hunter','twitter_watch')
    with pytest.raises(Blocked):first.begin('tracking','twitter_watch')
    second.finish(permit,402,quota=True)
    assert first.summary()['next_probe_at']==now[0]+7200
    now[0]+=7201
    permit=first.begin('tracking','twitter_watch');first.finish(permit,200)
    assert not second.summary()['quota_exhausted']


def test_global_daily_cap_counts_failures_and_all_programs(tmp_path,monkeypatch):
    monkeypatch.setenv('IKUN_6551_DAILY_LIMIT','3');now=[1792670000.0]
    ledger=Ledger(tmp_path/'ledger.db',clock=lambda:now[0])
    for program in ('tracking','hunter','hunter_ai'):
        p=ledger.begin(program,'twitter_user_info');ledger.finish(p,500,error='http_error')
    with pytest.raises(Blocked,match='daily_budget_exhausted'):ledger.begin('tracking','twitter_watch')
    status=ledger.summary();assert status['used']==3 and len(status['by_program'])==3
    now[0]+=86400;assert ledger.summary()['used']==0


def test_concurrent_programs_cannot_reserve_two_inflight_requests(tmp_path):
    ledger=Ledger(tmp_path/'ledger.db')
    def attempt(i):
        try:return ledger.begin('tracking' if i%2 else 'hunter','twitter_watch')
        except Blocked:return None
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
    assert sum(x is not None for x in results)==1


def test_recovery_job_is_once_per_generation_gap_and_never_paid_retry(tmp_path):
    ledger=Ledger(tmp_path/'ledger.db');row={'subscription_id':'sub_test','generation':2,'generation_at':10,'handle':'example'}
    ledger.mark_gap(20);ledger.close_gap(30,[row]);ledger.close_gap(31,[row])
    jobs=ledger.jobs('sub_test');assert len(jobs)==1 and (jobs[0]['from_at'],jobs[0]['to_at'])==(20,30)
    permit=ledger.begin('tracking','twitter_search',purpose='backfill',job_key=jobs[0]['key'])
    ledger.finish(permit,error='ReadTimeout')
    assert Ledger(ledger.path).jobs('sub_test')==[]
    with pytest.raises(Blocked,match='recovery_already_attempted'):
        ledger.begin('tracking','twitter_search',purpose='backfill',job_key=jobs[0]['key'])


def test_blocked_recovery_is_not_consumed_and_cache_is_shared(tmp_path):
    ledger=Ledger(tmp_path/'ledger.db');row={'subscription_id':'sub_test','generation':1,'generation_at':10,'handle':'example'}
    ledger.initial(row);ledger.initial(row);assert len(ledger.jobs('sub_test'))==1
    ledger.trip_quota(initial=True)
    with pytest.raises(Blocked):ledger.begin('tracking','twitter_user_tweets',purpose='backfill',job_key=ledger.jobs('sub_test')[0]['key'])
    assert len(ledger.jobs('sub_test'))==1
    payload={'success':True,'data':[{'twAccount':'Example','newTweetBol':True}]}
    ledger.cache_watch(payload);assert Ledger(ledger.path).cached_watch()==payload
    assert ledger.summary()['used']==0


def test_response_classification_and_logs_cannot_contain_secrets(tmp_path,caplog):
    response=httpx.Response(402,json={'success':False,'error':'insufficient quota','token':'PRIVATE_TOKEN'})
    assert quota_response(response)
    assert response_error(httpx.Response(200,text='not-json'))=='invalid_json'
    ledger=Ledger(tmp_path/'ledger.db');p=ledger.begin('hunter','twitter_watch')
    ledger.finish(p,402,quota=True,error='PRIVATE SECRET')
    assert 'PRIVATE' not in caplog.text
    assert 'PRIVATE' not in (tmp_path/'6551-status.json').read_text()


def test_wss_401_backoff_and_recovery_does_not_clear_paid_rest_circuit(tmp_path):
    from provider_6551 import wss_auth_delay
    assert [wss_auth_delay(n) for n in range(1,9)]==[60,120,240,480,600,600,600,600]
    ledger=Ledger(tmp_path/'ledger.db');ledger.trip_quota(initial=True)
    ledger.wss_rejected('tracking')
    assert ledger.summary()['realtime_paused']
    ledger.wss_recovered('tracking')
    assert not ledger.summary()['realtime_paused']
    assert ledger.summary()['quota_exhausted']
    with pytest.raises(Blocked):ledger.begin('hunter_ai','twitter_user_tweets')


def test_watch_cache_only_expires_on_event_and_manual_check_obeys_circuit(tmp_path):
    now=[1000.0];ledger=Ledger(tmp_path/'ledger.db',clock=lambda:now[0])
    ledger.request_watch_check();assert ledger.watch_pending()
    payload={'success':True,'data':[{'twAccount':'example'}]}
    ledger.cache_watch(payload);assert not ledger.watch_pending()
    now[0]+=7200
    assert ledger.cached_watch()==payload and not ledger.watch_pending()
    ledger.request_watch_check(force=True)
    assert ledger.cached_watch() is None and ledger.watch_pending()
    ledger.trip_quota(initial=True)
    with pytest.raises(Blocked):ledger.begin('tracking','twitter_watch')
    assert ledger.summary()['used']==0
