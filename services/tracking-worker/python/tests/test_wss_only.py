"""WSS-only policy is independent of quota availability and old pending jobs."""
import time
import pytest
from conftest import add,event,tweet
from tracking.remote import RemoteError
from tracking.worker import Worker


@pytest.mark.parametrize('switch,budget',[(None,None),('0','300'),('1','0')])
async def test_disabled_recovery_blocks_every_data_endpoint_before_transport(worker,vendor,monkeypatch,switch,budget):
    for key,value in (('IKUN_TRACKING_BACKFILL_ENABLED',switch),('IKUN_6551_BACKFILL_DAILY_LIMIT',budget)):
        if value is None:monkeypatch.delenv(key,raising=False)
        else:monkeypatch.setenv(key,value)
    for endpoint in ('twitter_user_tweets','twitter_search','twitter_user_info','twitter_user_by_id'):
        with pytest.raises(RemoteError,match='backfill_disabled'):
            await worker.remote.request(endpoint,{})
    assert vendor.calls==[] and worker.ledger.summary()['used']==0


async def test_new_account_restart_reconnect_and_pending_jobs_stay_passive(worker,store,vendor,monkeypatch):
    row=add(store)
    store.observe(row,claim='owned',status='running')
    row=store.get(row['project_id']);vendor.rows[row['handle']]=vendor.watch(row['handle'])
    worker.ledger.initial(row)
    existing=worker.ledger.jobs(row['subscription_id'])
    store.runtime(heartbeat=time.time()-30,pong_at=time.time()-35)
    monkeypatch.setenv('IKUN_TRACKING_BACKFILL_ENABLED','0')
    monkeypatch.setenv('IKUN_6551_BACKFILL_DAILY_LIMIT','0')
    restarted=Worker(worker.cfg,store,worker.remote)
    restarted._reconnected_at=time.time()
    async def pause(seconds):restarted.stop.set()
    monkeypatch.setattr(restarted,'pause',pause)
    await restarted.ticks()
    await restarted.backfill(row)
    assert worker.ledger.jobs(row['subscription_id'])==existing
    with worker.ledger.db() as db:
        assert db.execute("SELECT value FROM meta WHERE key='tracking_gap'").fetchone() is None
    assert all(name=='twitter_watch' for name,_ in vendor.calls)
    assert restarted.ingest(event(tweet(tweet_id='9012345')))
    assert store.activities()[0]['source']=='wss'
