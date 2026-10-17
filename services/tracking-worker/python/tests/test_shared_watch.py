import copy
from dataclasses import replace
import pytest
from conftest import add, event, tweet

async def test_shared_receive_and_remove_preserves_owner(worker, store, vendor):
    row = add(store)
    watch = vendor.watch('project1', group='ALPHA')
    watch.update(id=777, newFlwBol=True)
    vendor.rows['project1'] = watch
    before = copy.deepcopy(watch)
    worker.cfg = replace(worker.cfg, shared_watch_ids={'project1': '777'})
    await worker.reconcile()
    row = store.get(row['project_id'])
    assert row['status'] == 'running' and row['claim'] == 'none' and row['error'] is None
    assert worker.ingest(event(tweet()))
    store.mutate('remove', row['project_id'], {'expected_revision': row['revision']}, 'admin', 'shared-remove')
    await worker.reconcile()
    assert store.get(row['project_id'])['status'] == 'removed'
    assert not worker.ingest(event(tweet(tweet_id='99999')))
    assert vendor.rows['project1'] == before
    assert all(name == 'twitter_watch' for name, _ in vendor.calls)

@pytest.mark.parametrize('mode,code', [('missing','shared_watch_missing'), ('wrong','shared_watch_identity_changed'), ('disabled','shared_watch_not_enabled'), ('paused','shared_watch_not_enabled')])
async def test_shared_never_repairs_owner_watch(worker, store, vendor, mode, code):
    row = add(store)
    worker.cfg = replace(worker.cfg, shared_watch_ids={'project1':'777'})
    if mode != 'missing':
        watch = vendor.watch('project1', group='ALPHA')
        watch.update(id=778 if mode == 'wrong' else 777)
        if mode == 'disabled': watch['newTweetBol'] = False
        if mode == 'paused': watch['isPaused'] = True
        vendor.rows['project1'] = watch
    await worker.reconcile()
    assert store.get(row['project_id'])['error'] == code
    assert not worker.ingest(event(tweet()))
    assert all(name == 'twitter_watch' for name, _ in vendor.calls)
