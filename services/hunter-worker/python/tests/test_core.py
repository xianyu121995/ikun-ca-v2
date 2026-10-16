import json
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from hunterradar.config import Settings, read_env
from hunterradar.parsers import followings, profile, watch_coverage, wss_events, Target
from hunterradar.store import BudgetExceeded, Conflict, Store, WINDOW
from conftest import NOW, discover, event, ready, reviewed


def payload(content=None, **params):
    return {'method':'twitter.event','params':{'id':'e1','twAccount':'Hunter1','eventType':'NEW_FOLLOWER',
            'createdAt':datetime.fromtimestamp(NOW,timezone.utc).isoformat(),
            'content':content if content is not None else [{'twAccount':'Project1','twId':'999','createdAt':'2000-01-01T00:00:00Z'}],**params}}


@pytest.mark.parametrize('followers,mode', [(0,'REST'),(4999,'REST'),(5000,'WSS'),(5001,'WSS')])
def test_boundary(store,followers,mode):
    row = ready(store,followers=followers)
    assert row['mode']==mode and row['profile_status']=='ready'


@pytest.mark.parametrize('count', [None,-1,True,'unknown',3.4])
def test_unknown_count_is_not_5000(count):
    with pytest.raises(ValueError):
        profile({'data':{'userId':'123','followersCount':count}},'hunter1')


def test_profile_requires_stable_identity():
    with pytest.raises(ValueError):
        profile({'data':{'followersCount':5001}},'hunter1')
    with pytest.raises(ValueError):
        profile({'data':{'screenName':'other','userId':'1','followersCount':5}},'hunter1')


@pytest.mark.parametrize('as_string', [False,True])
def test_wss_direction_and_outer_event_time(as_string):
    message = payload()
    if as_string:
        message['params']['content'] = json.dumps(message['params']['content'])
    item = wss_events(message,NOW)[0]
    assert item.hunter=='hunter1' and item.target.username=='project1'
    assert item.occurred_at==pytest.approx(NOW)  # profile creation is not the follow timestamp


def test_multitarget_envelope_unique_keys():
    events = wss_events(payload([{'twAccount':'project1'},{'twAccount':'project2'}]), NOW)
    assert len(events)==2 and events[0].key!=events[1].key


@pytest.mark.parametrize('change', [{'eventType':'NEW_UNFOLLOWER'},{'eventType':'NEW_TWEET'}])
def test_not_a_follow(change):
    assert wss_events(payload(**change), NOW)==[]


@pytest.mark.parametrize('change', [{'createdAt':'2000-01-01T00:00:00Z'}, {'createdAt':'2100-01-01T00:00:00Z'}, {'createdAt':None}, {'content':'{}'}, {'twAccount':'../../secret'}])
def test_reject_bad_wss(change):
    with pytest.raises((ValueError,TypeError)):
        wss_events(payload(**change),NOW)


def test_unknown_and_disabled_hunters_do_not_ingest(store):
    assert not store.ingest_wss(event())
    row = ready(store)
    store.patch(row['id'],row['version'],enabled=False)
    assert not store.ingest_wss(event())


def test_same_hunter_repeated_is_one(store):
    ready(store)
    assert store.ingest_wss(event())
    assert not store.ingest_wss(event())
    assert store.ingest_wss(event(key='refollow',at=NOW+1,received=NOW+1))
    assert store.aggregate(NOW+1)==[]


def test_two_distinct_hunters_cross_provider_id_mismatch(store):
    ready(store,'hunter1',user_id='101')
    second=ready(store,'hunter2',followers=4999,user_id='102')
    store.apply_poll(second,[Target('old','7')],NOW-10)
    store.ingest_wss(event(target_id='111'))
    with pytest.raises(Conflict,match='identity_conflict'):
        store.apply_poll(second,[Target('project1','222')],NOW)
    assert store.aggregate(NOW)==[]


def test_72_hour_boundary_and_expiry(store):
    ready(store,'hunter1',user_id='101')
    ready(store,'hunter2',user_id='102')
    store.ingest_wss(event(at=NOW-WINDOW))
    store.ingest_wss(event('hunter2'))
    assert len(store.aggregate(NOW))==1
    assert store.aggregate(NOW+0.01)==[]


def test_rest_baseline_reorder_duplicates_restart(store):
    row=ready(store,followers=100)
    a,b,c=Target('a','1'),Target('b','2'),Target('c','3')
    first=store.apply_poll(row,[a,b],NOW)
    assert first['baseline'] and first['new']==0
    assert store.apply_poll(row,[b,a],NOW+3600)['new']==0
    store=Store(store.path)
    assert store.apply_poll(row,[c,b],NOW+7200)['new']==1
    assert store.apply_poll(row,[c,a],NOW+10800)['new']==0
    assert store.status()['events']==1


def test_empty_baseline_is_valid(store):
    row=ready(store,followers=10)
    assert store.apply_poll(row,[],NOW)['baseline']
    assert store.apply_poll(row,[Target('new','1')],NOW+1)['new']==1


def test_full_page_and_gap_warn(store):
    row=ready(store,followers=10)
    targets=[Target('p'+str(i),str(i)) for i in range(20)]
    assert store.apply_poll(row,targets,NOW)['warning']=='latest_20_may_miss_followings'
    assert store.apply_poll(row,targets,NOW+8000)['warning']=='poll_gap_may_miss_followings'


def test_disable_inflight_poll_and_reenable_baseline(store):
    row=ready(store,followers=10)
    store.apply_poll(row,[Target('old','1')],NOW)
    disabled=store.patch(row['id'],row['version'],enabled=False)
    assert store.apply_poll(row,[Target('new','2')],NOW+10)['discarded']
    enabled=store.patch(row['id'],disabled['version'],enabled=True)
    assert not store.apply_profile(row,'101','hunter1',10,NOW+10)
    store.apply_profile(enabled,'101','hunter1',10,NOW+10)
    fresh=store.hunter(row['id'])
    assert store.apply_poll(fresh,[Target('new','2')],NOW+20)['baseline']
    assert store.status()['events']==0


def test_initial_channel_remains_fixed_after_profile_change(store):
    row=ready(store,followers=4999)
    assert not store.apply_profile(row,row['user_id'],'hunter1',5000,NOW+10)
    assert store.hunter(row['id'])['mode']=='REST'
    disabled=store.patch(row['id'],row['version'],enabled=False)
    enabled=store.patch(row['id'],disabled['version'],enabled=True,recheck=True)
    assert enabled['profile_status']=='ready' and enabled['mode']=='REST'
    assert enabled['next_profile_at']==9999999999


def test_duplicate_stable_id_cannot_fake_two_hunters(store):
    ready(store,'hunter1',user_id='101')
    row=store.add('alias')
    with pytest.raises(Conflict):
        store.apply_profile(row,'101','alias',5001,NOW)
    assert store.hunter(row['id'])['profile_status']=='pending'


def test_delete_preserves_history_readd_identity(store):
    discover(store)
    row=store.hunters()[0]
    store.patch(row['id'],row['version'],delete=True)
    assert len(store.aggregate(NOW))==1
    restored=store.add(row['username'])
    assert restored['id']==row['id'] and restored['generation']>row['generation']


def test_optimistic_hunter_version(store):
    row=store.add('Hunter1')
    assert store.add('@hunter1')['id']==row['id']
    store.patch(row['id'],1,note='test')
    with pytest.raises(Conflict):
        store.patch(row['id'],1,enabled=False)


def test_confirm_only_after_review_and_idempotent(store):
    item=discover(store)
    with pytest.raises(Conflict):
        store.confirm('project1',item['version'],'key1','admin',NOW)
    item=store.review('project1',1,{'name':'P','description':'','website':'','notes':'','rating':'A'},'admin',NOW)
    task=store.confirm('project1',item['version'],'key1','admin',NOW)
    assert store.confirm('project1',item['version'],'key1','admin',NOW)['id']==task['id']
    with pytest.raises(Conflict):
        store.confirm('project1',item['version']+1,'key1','admin',NOW)
    with store.connect() as db:
        raw=db.execute('SELECT body FROM task_outbox').fetchone()[0]
    assert 'hunter1' not in raw and 'hunter2' not in raw and 'confirmed_by' not in raw


def test_expired_target_cannot_confirm(store):
    item=reviewed(store)
    with pytest.raises(Conflict):
        store.confirm('project1',item['version'],'key','admin',NOW+WINDOW+1)


def test_outbox_crash_recovery(store):
    item=reviewed(store)
    task=store.confirm('project1',item['version'],'key','admin',NOW)
    claimed=store.claim_task(NOW)
    assert claimed['attempts']==1
    assert store.claim_task(NOW) is None
    store=Store(store.path)
    store.recover()
    assert store.claim_task(NOW)['id']==task['id']


def test_quota_persistence_minute_and_day_rollover(store):
    store.reserve('test',60,120,2,NOW)
    Store(store.path).reserve('test',60,120,2,NOW)
    with pytest.raises(BudgetExceeded):
        store.reserve('test',60,120,2,NOW)
    with pytest.raises(BudgetExceeded):
        store.reserve('test',60,120,2,NOW+61)
    store.reserve('test',60,120,2,(int(NOW)//86400+1)*86400)


def test_database_boundary(tmp_path):
    folder=tmp_path.resolve()
    for name in ('tracking.db','projects.db'):
        with pytest.raises(ValueError):
            Store(folder/name)
        assert not (folder/name).exists()
    path=folder/'hunter.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE foreign_table(id)')
    before=path.read_bytes()
    with pytest.raises(ValueError):
        Store(path)
    assert path.read_bytes()==before


def test_symlink_and_hardlink_boundary(tmp_path):
    folder=tmp_path.resolve()
    folder.joinpath('real').mkdir(mode=0o700)
    folder.joinpath('alias').symlink_to(folder/'real',target_is_directory=True)
    with pytest.raises(ValueError):
        Store(folder/'alias'/'hunter.db')
    original=Store(folder/'real'/'hunter.db',initialize=True)
    os.link(original.path,folder/'hunter.db')
    with pytest.raises(ValueError):
        Store(folder/'hunter.db')


def test_single_worker(store):
    owner=store.acquire_worker()
    try:
        with pytest.raises(RuntimeError):
            store.acquire_worker()
    finally:
        store.release_worker(owner)
    store.release_worker(store.acquire_worker())


def test_stale_worker_is_fenced(store):
    from hunterradar.store import LeaseLost
    old=store.acquire_worker()
    worker=store.worker_view(old)
    with store.connect(True) as db:
        db.execute('UPDATE worker_lease SET expires_at=0')
    new=store.acquire_worker()
    with pytest.raises(LeaseLost):
        worker.set_state('should_not_write','old_owner')
    store.release_worker(old)
    store.worker_view(new).renew_worker()
    store.release_worker(new)


def test_followings_contract_and_watch():
    assert followings({'followings':[{'userName':'Target','id':'123'}]})[0].username=='target'
    with pytest.raises(ValueError):
        followings({'followers':[]})
    assert watch_coverage({'data':[{'twAccount':'Hunter1','newFlwBol':True},{'twAccount':'Other','newFlwBol':False}]})=={'hunter1'}


def test_env_parser_never_executes(tmp_path):
    file=tmp_path/'env'
    file.write_text('SECRET=$(touch bad)\nKEY="hello"\n')
    assert read_env(file)['SECRET']=='$(touch bad)'
    assert read_env(file)['KEY']=='hello'


def test_settings_safe_urls():
    with pytest.raises(ValueError):
        Settings(host='0.0.0.0')
    with pytest.raises(ValueError):
        Settings(project_url='http://evil.example/tasks',project_secret='s'*32)
    Settings(project_url='http://127.0.0.1:9000/tasks',project_secret='s'*32)


def test_foundation_hunter_database_upgrade_and_checksum(tmp_path):
    path=tmp_path.resolve()/'hunter.db'
    from hunterradar.store import APP_ID
    with sqlite3.connect(path) as db:
        db.execute(f'PRAGMA application_id={APP_ID}')
        db.executescript('CREATE TABLE _store_identity(singleton INTEGER PRIMARY KEY, store_name TEXT); INSERT INTO _store_identity VALUES(1,\'hunter\'); CREATE TABLE _schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT); INSERT INTO _schema_migrations VALUES(1,\'foundation\',\'2026-10-15\');')
    os.chmod(path,0o600)
    store=Store(path,initialize=True)
    with store.connect() as db:
        assert db.execute('SELECT version FROM _schema_migrations ORDER BY version').fetchall()[-1][0]==5
        assert db.execute('PRAGMA user_version').fetchone()[0]==5
        db.execute("UPDATE _hunter_migrations SET checksum='tampered'")
    with pytest.raises(ValueError,match='checksum'):
        Store(path)
