from types import SimpleNamespace
import pytest
from hunterradar.watch import synchronize,FLAGS
from conftest import ready

class Vendor:
    def __init__(self,rows=None):self.rows=rows or {};self.writes=[]
    async def request(self,operation):return {'success':True,'data':list(self.rows.values())}
    async def watch_write(self,op,body):
        self.writes.append((op,body));name=body['username']
        if op=='twitter_watch_add':self.rows[name]={'twAccount':name,'id':100,**body}
        else:self.rows.pop(name)

@pytest.mark.asyncio
async def test_add_reconcile_delete_only_created_watch(store):
    h=ready(store);v=Vendor();e=SimpleNamespace(store=store,providers=v)
    await synchronize(e);assert v.rows[h['username']]['newFlwBol'] is True
    await synchronize(e);assert len(v.writes)==1
    row=store.hunter(h['id']);store.patch(h['id'],row['version'],delete=True)
    await synchronize(e);assert v.rows=={} and len(v.writes)==2

@pytest.mark.asyncio
async def test_existing_shared_watch_not_modified_or_deleted(store):
    h=ready(store);watch={'twAccount':h['username'],'id':200,'remark':'ALPHA',**{f:f=='newTweetBol' for f in FLAGS}}
    v=Vendor({h['username']:watch});e=SimpleNamespace(store=store,providers=v)
    await synchronize(e);assert not v.writes and store.states()['watch_error']=='existing_watch_owned_elsewhere'
    store.patch(h['id'],h['version'],delete=True);await synchronize(e);assert v.rows[h['username']]==watch and not v.writes

@pytest.mark.asyncio
async def test_shared_six_hundred_pool_counts_non_tweet_watches(store):
    ready(store);v=Vendor({str(i):{'twAccount':str(i),'newTweetBol':False} for i in range(600)})
    await synchronize(SimpleNamespace(store=store,providers=v));assert not v.writes and store.states()['watch_error']=='quota_exhausted'

@pytest.mark.asyncio
async def test_approved_existing_flag_retains_other_flags_on_remove(store):
    h=ready(store);v=Vendor({h['username']:{'twAccount':h['username'],'id':100,'newFlwBol':False,'newTweetBol':True,'remark':'original',**{f:False for f in FLAGS if f not in ('newFlwBol','newTweetBol')}}})
    store.set_state('approved_flag:'+h['id'],{'id':'100'})
    engine=SimpleNamespace(store=store,providers=v)
    await synchronize(engine);assert v.rows[h['username']]['newFlwBol'] is True and v.rows[h['username']]['newTweetBol'] is True
    row=store.hunter(h['id']);store.patch(h['id'],row['version'],delete=True)
    await synchronize(engine);assert v.rows[h['username']]['newFlwBol'] is False and v.rows[h['username']]['newTweetBol'] is True
    assert all(op!='twitter_watch_delete' for op,body in v.writes)
