import copy,json
from dataclasses import replace
import pytest
from conftest import add,event,tweet

async def test_adopt_preserves_extra_flags_audits_once_and_only_joined_accounts(worker,store,vendor):
    row=add(store)
    watch=vendor.watch('project1',group='ALPHA');watch.update(id=919,newFlwBol=True,remark='legacy')
    other=vendor.watch('notjoined',group='ALPHA');other.update(id=920,newFlwBol=True)
    vendor.rows.update(project1=watch,notjoined=other)
    before=copy.deepcopy(vendor.rows)
    worker.cfg=replace(worker.cfg,adoptable_handles=['project1','notjoined'])
    await worker.reconcile();await worker.reconcile()
    saved=store.get(row['project_id'])
    assert saved['claim']=='owned' and saved['status']=='running' and not saved['error']
    assert saved['baseline_ready'] and vendor.rows==before
    assert all(name=='twitter_watch' for name,_ in vendor.calls)
    assert worker.ingest(event(tweet()))
    with store.connect() as db:
        audit=db.execute("SELECT detail FROM audit WHERE action='watch_adopted'").fetchall()
    assert len(audit)==1 and json.loads(audit[0][0])['watch_id']=='919'
    # Explicit stop/remove now owns deletion, while an unjoined ALPHA account remains untouched.
    store.mutate('stop',row['project_id'],{'expected_revision':saved['revision']},'admin','adopt-stop')
    await worker.reconcile()
    assert 'project1' not in vendor.rows and vendor.rows['notjoined']==before['notjoined']
    saved=store.get(row['project_id'])
    store.mutate('resume',row['project_id'],{'expected_revision':saved['revision']},'admin','adopt-resume')
    await worker.reconcile();saved=store.get(row['project_id'])
    assert saved['status']=='running' and vendor.rows['project1']['newTweetBol']
    store.mutate('remove',row['project_id'],{'expected_revision':saved['revision']},'admin','adopt-remove')
    await worker.reconcile()
    assert store.get(row['project_id'])['status']=='removed' and 'project1' not in vendor.rows
    assert vendor.rows['notjoined']==before['notjoined']

async def test_unlisted_existing_watch_still_conflicts(worker,store,vendor):
    row=add(store);vendor.rows['project1']=vendor.watch('project1',group='ALPHA')
    worker.cfg=replace(worker.cfg,adoptable_handles=['someoneelse'])
    before=copy.deepcopy(vendor.rows)
    await worker.reconcile()
    assert store.get(row['project_id'])['error']=='ownership_conflict'
    assert vendor.rows==before and all(name=='twitter_watch' for name,_ in vendor.calls)

async def test_shared_has_priority_even_if_adoption_list_is_misconfigured(worker,store,vendor):
    row=add(store);w=vendor.watch('project1',group='ALPHA');w.update(id=777,newFlwBol=True)
    vendor.rows['project1']=w;before=copy.deepcopy(w)
    worker.cfg=replace(worker.cfg,shared_watch_ids={'project1':'777'},adoptable_handles=['project1'])
    await worker.reconcile();saved=store.get(row['project_id'])
    assert saved['status']=='running' and saved['claim']=='none'
    store.mutate('remove',row['project_id'],{'expected_revision':saved['revision']},'admin','shared-safe-remove')
    await worker.reconcile()
    assert vendor.rows['project1']==before and all(name=='twitter_watch' for name,_ in vendor.calls)

async def test_adoption_does_not_silently_enable_tweets(worker,store,vendor):
    row=add(store);w=vendor.watch('project1',group='ALPHA');w.update(id=919,newTweetBol=False,newFlwBol=True)
    vendor.rows['project1']=w;before=copy.deepcopy(w)
    worker.cfg=replace(worker.cfg,adoptable_handles=['project1'])
    await worker.reconcile()
    assert store.get(row['project_id'])['error']=='adopted_watch_not_enabled'
    assert vendor.rows['project1']==before and all(name=='twitter_watch' for name,_ in vendor.calls)

async def test_new_policy_requeues_conflict_without_clearing_it(worker,store,vendor):
    row=add(store);w=vendor.watch('project1',group='ALPHA');w.update(id=919)
    vendor.rows['project1']=w
    await worker.reconcile()
    assert store.get(row['project_id'])['error']=='ownership_conflict'
    worker.cfg=replace(worker.cfg,adoptable_handles=['project1'])
    worker.retry_adoptions()
    current=store.get(row['project_id'])
    assert current['next_retry']==0 and current['error']=='ownership_conflict'
    await worker.reconcile()
    assert store.get(row['project_id'])['status']=='running' and not store.get(row['project_id'])['error']
