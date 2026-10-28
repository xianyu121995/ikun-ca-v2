"""Delivered joins learn the projects command outcome without posting again."""
import httpx

from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.formal import FormalService
from hunterradar.providers import Providers
from conftest import NOW
from test_b4 import confirm

PROJECT='prj_00000000-0000-4000-8000-0000000000aa'


def delivered(store):
    command,task=confirm(store)
    store.finish_task(task['id'],'delivered',receipt='fixture-receipt',now=NOW,canonical=PROJECT,receipt_data={
        'event_id':task['event_id'],'command_id':task['command_id'],'project_id':PROJECT,
        'receipt_id':'fixture-receipt','accepted_at':'2026-10-15T00:00:00Z','duplicate':True})
    with store.connect(True) as db:
        db.execute('UPDATE task_outbox SET posted=1 WHERE id=?',(task['id'],))
        row=dict(db.execute('SELECT * FROM task_outbox WHERE id=?',(task['id'],)).fetchone())
    assert row['status']=='delivered' and row['posted']==1 and row['public_state']=='pending' and row['attempts']==1
    return command,row


def engine(store,handler):
    settings=Settings(db=store.path,project_url='http://127.0.0.1/internal/v1/ingest/hunter',delivery_protocol='v2-event',project_token='r'*32)
    client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return settings,Engine(settings,store,Providers(settings,store,client)),client


def snapshot(store):
    with store.connect() as db:
        row=dict(db.execute('SELECT status,posted,attempts,public_state,last_error,command_revision FROM task_outbox').fetchone())
        row['tasks']=db.execute('SELECT count(*) FROM task_outbox').fetchone()[0]
        row['changes']=db.execute("SELECT count(*) FROM public_changes WHERE type='command.updated'").fetchone()[0]
        return row


async def reconcile(store,state,error,now=NOW):
    command,row=delivered(store)
    calls=[]
    def handler(request):
        calls.append((request.method,str(request.url)))
        body={'event_id':row['event_id'],'command_id':row['command_id'],'project_id':PROJECT,'receipt_id':'fixture-receipt',
              'accepted_at':'2026-10-15T00:00:00Z','duplicate':True,'command_state':state,'error_code':error}
        return httpx.Response(200,json={'data':body})
    settings,worker,client=engine(store,handler)
    async with client:
        assert await worker.reconcile_outcomes(now)==1
    return command,row,calls,snapshot(store)


async def test_delivered_succeeded_shows_tracking(store):
    command,row,calls,after=await reconcile(store,'succeeded',None)
    assert after['public_state']=='succeeded' and after['last_error'] is None
    assert FormalService(store).discovery(row['discovery_id'],NOW)['monitoring_state']=='succeeded'
    assert after['status']=='delivered' and after['posted']==1 and after['attempts']==1 and after['tasks']==1
    assert calls==[('GET','http://127.0.0.1/internal/v1/receipts/hunter/'+row['event_id'])]
    assert store.claim_task(NOW+10**6) is None
    again=[]
    def handler(request):
        again.append(request.method)
        return httpx.Response(500)
    settings,worker,client=engine(store,handler)
    async with client:
        assert await worker.reconcile_outcomes(NOW+10**6)==0
    assert again==[] and snapshot(store)['command_revision']==after['command_revision']
    assert snapshot(store)['attempts']==1 and snapshot(store)['tasks']==1
    assert FormalService(store).command(command['command_id'],'query')['state']=='succeeded'


async def test_delivered_failed_shows_failed(store):
    command,row,calls,after=await reconcile(store,'failed','ABANDONED_INVALID_ID_V5')
    assert after['public_state']=='failed' and after['last_error']=='ABANDONED_INVALID_ID_V5'
    assert FormalService(store).discovery(row['discovery_id'],NOW)['monitoring_state']=='failed'
    assert after['status']=='delivered' and after['posted']==1 and after['attempts']==1 and after['tasks']==1
    assert all(method=='GET' for method,_ in calls) and store.claim_task(NOW+10**6) is None
    before=after['command_revision']
    _,_,_,second=await reconcile_again(store,row,'failed','ABANDONED_INVALID_ID_V5',NOW+10**6)
    assert second['command_revision']==before and second['attempts']==1 and second['tasks']==1
    assert FormalService(store).command(command['command_id'],'query')['state']=='failed'


async def reconcile_again(store,row,state,error,now):
    calls=[]
    def handler(request):
        calls.append(request.method)
        body={'event_id':row['event_id'],'command_id':row['command_id'],'project_id':PROJECT,'receipt_id':'fixture-receipt',
              'accepted_at':'2026-10-15T00:00:00Z','duplicate':True,'command_state':state,'error_code':error}
        return httpx.Response(200,json={'data':body})
    settings,worker,client=engine(store,handler)
    async with client:
        count=await worker.reconcile_outcomes(now)
    return calls,count,None,snapshot(store)


async def test_unknown_timeout_and_ownership_stay_unverified_and_idempotent(store):
    command,row,calls,after=await reconcile(store,'unknown','UPSTREAM_TIMEOUT')
    assert after['public_state']=='unknown' and after['last_error']=='UPSTREAM_TIMEOUT'
    assert FormalService(store).discovery(row['discovery_id'],NOW)['monitoring_state']=='unknown'
    assert after['attempts']==1 and after['posted']==1 and after['status']=='delivered' and after['tasks']==1
    assert store.claim_task(NOW+10**6) is None
    early,_count,_,quiet=await reconcile_again(store,row,'unknown','UPSTREAM_TIMEOUT',NOW+30)
    assert early==[] and quiet['command_revision']==after['command_revision'] and quiet['public_state']=='unknown'
    later,count,_,same=await reconcile_again(store,row,'unknown','UPSTREAM_TIMEOUT',NOW+10**6)
    assert later==['GET'] and count==1 and same['command_revision']==after['command_revision'] and same['attempts']==1 and same['tasks']==1
    # A different unknown code still does not enqueue, and a later success can replace unknown.
    moved,_,_,promoted=await reconcile_again(store,row,'unknown','ownership_conflict',NOW+2*10**6)
    assert moved==['GET'] and promoted['public_state']=='unknown' and promoted['last_error']=='ownership_conflict'
    assert promoted['attempts']==1 and store.claim_task(NOW+10**7) is None
    done,_,_,final=await reconcile_again(store,row,'succeeded',None,NOW+3*10**6)
    assert done==['GET'] and final['public_state']=='succeeded' and final['last_error'] is None
    assert final['attempts']==1 and final['tasks']==1 and final['status']=='delivered' and store.claim_task(NOW+10**8) is None


async def test_reconcile_ignores_undelivered_rows(store):
    command,task=confirm(store)
    calls=[]
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200,json={'data':{'command_state':'succeeded'}})
    settings,worker,client=engine(store,handler)
    async with client:
        assert await worker.reconcile_outcomes(NOW)==0
    assert calls==[] and task['attempts']==1
    with store.connect() as db:
        row=dict(db.execute('SELECT status,posted,public_state FROM task_outbox').fetchone())
    assert row=={'status':'delivering','posted':0,'public_state':'pending'}
    assert FormalService(store).command(command['command_id'],'query')['state']=='pending'


async def test_transport_error_does_not_fail_or_repost(store):
    command,row=delivered(store)
    calls=[]
    def down(request):
        calls.append(request.method)
        raise httpx.ConnectError('projects down')
    settings,worker,client=engine(store,down)
    async with client:
        assert await worker.reconcile_outcomes(NOW+1)==1
    after=snapshot(store)
    assert calls==['GET'] and after['public_state']=='pending' and after['status']=='delivered' and after['attempts']==1 and after['tasks']==1
    assert store.claim_task(NOW+10**6) is None
    assert FormalService(store).discovery(row['discovery_id'],NOW)['monitoring_state']=='pending'
    assert FormalService(store).command(command['command_id'],'query')['state']=='pending'
