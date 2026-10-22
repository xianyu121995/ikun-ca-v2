import json
import time
import pytest
from conftest import add,event,tweet
from wss_audit import WssAudit


def reasons(caplog):
    return [json.loads(r.message).get('reason') for r in caplog.records if r.name=='ikun.wss.receive']


def prepare(store):
    row=add(store)
    store.observe(row,remote_state='active',observed_at=time.time(),claim='owned',status='running',baseline_ready=1)
    return store.get(row['project_id'])


def ingest(worker,message):return worker.ingest(message,WssAudit('tracking').frame(message))


def test_accepted_and_duplicate_keep_original_store_behavior(worker,store,caplog):
    prepare(store);message=event(tweet(text='PRIVATE_BODY',tweet_id='89101'))
    assert ingest(worker,message)
    assert not ingest(worker,message)
    assert len(store.activities())==1
    assert 'stored_or_enriched' in reasons(caplog) and 'duplicate_or_no_change' in reasons(caplog)
    assert 'PRIVATE_BODY' not in caplog.text


@pytest.mark.parametrize('case,reason',[
    ('not_subscribed','not_subscribed'),('missing_author','author_handle_missing_or_mismatch'),
    ('author_id','author_id_missing_or_mismatch'),('unsupported','not_tracking_tweet_event'),
])
def test_existing_rejections_have_reasons(worker,store,caplog,case,reason):
    row=prepare(store);message=event(tweet(text='PRIVATE_BODY',tweet_id='89102'))
    if case=='not_subscribed':message=event(tweet('unknown'),username='unknown')
    if case=='stale':store.observe(row,observed_at=time.time()-1000)
    if case=='not_active':store.observe(row,remote_state='unknown')
    if case=='missing_author':message['params']['content'].pop('userScreenName')
    if case=='author_id':
        with store.connect() as db:db.execute('UPDATE projects SET x_user_id=? WHERE project_id=?',('100',row['project_id']))
    if case=='unsupported':message['params']['eventType']='CA'
    assert not ingest(worker,message)
    assert reason in reasons(caplog)
    assert not store.activities()
    assert 'PRIVATE_BODY' not in caplog.text


@pytest.mark.parametrize('error', ['api_failure','quota_exhausted','rate_limited',None])
def test_rest_failure_or_stale_observation_never_blocks_authorized_wss(worker,store,caplog,error):
    row=prepare(store)
    store.observe(row,remote_state='unknown',status='retrying',error=error,observed_at=time.time()-86400)
    assert ingest(worker,event(tweet(tweet_id='89104')))
    assert 'watch_not_active' not in reasons(caplog)
    assert 'watch_observation_stale' not in reasons(caplog)


async def test_emergency_rest_pause_makes_no_provider_requests(worker,vendor,monkeypatch):
    from tracking.remote import RemoteError
    monkeypatch.setenv('IKUN_6551_REST_PAUSED','1')
    with pytest.raises(RemoteError,match='quota_exhausted'):
        await worker.remote.watches()
    assert vendor.calls==[]


def test_broken_diagnostic_callback_does_not_change_normalization_or_storage(store):
    from tracking.events import normalize
    row=prepare(store)
    def broken(reason):raise RuntimeError('logging failed')
    valid=normalize(tweet(tweet_id='89103'),'project1',on_drop=broken)
    assert store.insert_tweet(row,valid,'wss',on_drop=broken)
    assert not store.insert_tweet(row,valid,'wss',on_drop=broken)
    assert normalize({},'project1',on_drop=broken) is None
