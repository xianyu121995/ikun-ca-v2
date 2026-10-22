"""Approved night increment: synthetic Hunter-only PATCH/retention/recovery evidence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

import httpx
import pytest

from hunterradar.config import Settings
from hunterradar.engine import Engine
from hunterradar.formal import FormalService
from hunterradar.migration import APP_ID,FILES,NAMES,SQL_ROOT,LATEST_VERSION,checksums,migrate,statements
from hunterradar.protocol import Failure,canonical
from hunterradar.providers import Providers
from hunterradar.retention import TTL_US,WINDOW_US,backup_bundle,micros,restore_bundle,validate_bundle
from hunterradar.store import Conflict,Missing,Store
from conftest import NOW,discover,event,ready
from test_b4 import ADMIN,USER,client,confirm,headers

def resource(store):
    dto=FormalService(store).discovery(discover(store)['discovery_id'],NOW)
    return dto,'/api/v1/hunter/discoveries/'+dto['discovery_id']

def write(store,path,body,revision,key=None,now=NOW,actor=ADMIN):
    return FormalService(store).write(actor,'PATCH',path,body,key or str(uuid.uuid4()),f'"rev-{revision}"','fixture-research',now)

def count(store,table):
    with store.connect() as db:return db.execute('SELECT count(*) FROM '+table).fetchone()[0]

def test_research_persist_minimal_receipt_and_no_side_effects(store):
    dto,path=resource(store);key=str(uuid.uuid4())
    body={'name':'Synthetic Research','rating':'S','notes':'private research <script>inert()</script>','progress_stage':'researching','progress_percent':0,'token_date':'2028-02-29','token_date_status':'estimated'}
    first=write(store,path,body,dto['revision'],key)
    assert first[0]==200 and set(first[1])=={'discovery_id','revision','saved_at'} and first[2]==f'"rev-{dto["revision"]+1}"'
    assert write(store,path,dict(reversed(list(body.items()))),dto['revision'],key)==first
    current=FormalService(Store(store.path)).discovery(dto['discovery_id'],NOW)
    assert current['project']['rating']=='S' and current['project']['notes']==body['notes']
    assert current['project']['token_date']=='2028-02-29' and current['revision']==dto['revision']+1
    assert current['project_id'] is None and count(store,'task_outbox')==0
    with store.connect() as db:
        receipt=db.execute('SELECT response_json FROM operation_receipts').fetchone()[0]
        audit=db.execute("SELECT detail FROM audit WHERE action='discovery.research.patch'").fetchall()
        assert len(audit)==1 and body['notes'] not in audit[0][0] and body['notes'] not in receipt
        assert db.execute('SELECT count(*) FROM public_changes WHERE initial_publication=1').fetchone()[0]==1
        assert all('hunter1' not in r[0] and 'hunter2' not in r[0] for r in db.execute('SELECT data FROM public_changes'))

@pytest.mark.parametrize('field,value',[
 ('name','x'*120),('description','x'*4000),('notes','x'*4000),('category','x'*80),
 ('website_url','https://example.org/'+'x'*(2048-len('https://example.org/'))),
 ('rating','D'),('rating',None),('progress_percent',100),('progress_percent',None),
 ('category',None),('website_url',None),('description',''),('notes','')])
def test_patch_valid_field_boundaries(store,field,value):
    dto,path=resource(store);result=write(store,path,{field:value},dto['revision'])
    assert result[0]==200 and FormalService(store).discovery(dto['discovery_id'],NOW)['project'][field]==value

@pytest.mark.parametrize('body',[
 {},{'name':''},{'name':'  '},{'name':None},{'name':'x'*121},{'notes':None},{'notes':'x'*4001},
 {'description':None},{'description':'x'*4001},{'category':'x'*81},
 {'website_url':''},{'website_url':'javascript:alert(1)'},{'website_url':'https://user:pass@example.org'},
 {'website_url':'https://example.org/ bad'},{'website_url':'https://example.org/'+'x'*2048},
 {'rating':'unrated'},{'rating':'待定'},{'rating':1},{'rating':'a'},
 {'progress_percent':-0.01},{'progress_percent':100.01},{'progress_percent':True},{'progress_percent':'1'},
 {'progress_percent':float('nan')},{'progress_percent':float('inf')},
 {'progress_stage':None},{'progress_stage':'mainnet'},{'token_date':'2027-02-29','token_date_status':'confirmed'},
 {'token_date':'2028-02-29'},{'token_date':None,'token_date_status':'confirmed'},
 {'token_date':'2028-02-29T00:00:00Z','token_date_status':'confirmed'},
 {'discovery_id':'forged'},{'project_id':'prj_fake'},{'x_user_id':'123'},{'tenant_id':'other'},{'actor':'forged'},
 {'ignored':'yes'},{'revision':1},{'review_state':'reviewed'},{'followers':5000},
])
def test_patch_invalid_fields_atomic(store,body):
    from pydantic import ValidationError
    dto,path=resource(store)
    with pytest.raises((ValueError,ValidationError)):write(store,path,body,dto['revision'])
    assert FormalService(store).discovery(dto['discovery_id'],NOW)['revision']==dto['revision']
    assert count(store,'operation_receipts')==0 and count(store,'task_outbox')==0

@pytest.mark.parametrize('raw',['{"notes":"a","notes":"b"}','{"progress_percent":NaN}','[]','{}'])
def test_json_validation_at_formal_transport(store,raw):
    dto,path=resource(store)
    with client(store) as c:
        r=c.patch(path,content=raw,headers=headers()|{'content-type':'application/json','idempotency-key':str(uuid.uuid4()),'if-match':f'"rev-{dto["revision"]}"'})
    assert r.status_code==422 and count(store,'operation_receipts')==0

@pytest.mark.parametrize('one,two',[(1,1.0),(-0.0,0)])
def test_idempotency_numeric_normalization(store,one,two):
    dto,path=resource(store);key=str(uuid.uuid4())
    result=write(store,path,{'progress_percent':one},dto['revision'],key)
    assert write(store,path,{'progress_percent':two},dto['revision'],key)==result
    with pytest.raises(Failure) as e:write(store,path,{'progress_percent':two},dto['revision']+1,key)
    assert e.value.code=='IDEMPOTENCY_CONFLICT'

def test_revision_keys_authorization_and_replay_revocation(store):
    dto,path=resource(store)
    with client(store) as c:
        for actor in (USER,):assert c.patch(path,json={'rating':'A'},headers=headers(actor)).status_code==403
        assert c.patch(path,json={'rating':'A'}).status_code==401
        assert c.patch(path,json={'rating':'A'},headers=headers()|{'idempotency-key':str(uuid.uuid4())}).status_code==428
        assert c.patch(path,json={'rating':'A'},headers=headers()|{'idempotency-key':'invalid','if-match':'"rev-1"'}).status_code==422
        assert c.patch(path,json={'rating':'A'},headers=headers()|{'idempotency-key':str(uuid.uuid4()),'if-match':'W/"rev-1"'}).status_code==422
        key=str(uuid.uuid4());h=headers()|{'idempotency-key':key,'if-match':f'"rev-{dto["revision"]}"'}
        assert c.patch(path,json={'rating':'A'},headers=h).status_code==200
        assert c.patch(path,json={'rating':'A'},headers=headers(USER)|{'idempotency-key':key,'if-match':h['if-match']}).status_code==403
        assert c.patch(path,json={'rating':'B'},headers=h).json()['error']['code']=='IDEMPOTENCY_CONFLICT'
        assert c.patch(path,json={'rating':'B'},headers=h|{'idempotency-key':str(uuid.uuid4())}).json()['error']['code']=='VERSION_CONFLICT'

def test_concurrent_patch_only_one_commits(store):
    dto,path=resource(store)
    def call(rating):
        try:return write(store,path,{'rating':rating},dto['revision'])[0]
        except Failure as e:return e.status
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(call,['A','B']))==[200,409]
    assert count(store,'operation_receipts')==1

def test_confirm_then_research_cannot_reconfirm_changed_draft_as_original(store):
    command,task=confirm(store);service=FormalService(store)
    before={k:task[k] for k in ('id','command_id','event_id','body','body_hash','request_hash')}
    identifier=task['discovery_id'];dto=service.discovery(identifier,NOW);path='/api/v1/hunter/discoveries/'+identifier
    original=json.loads(task['body'])['payload']['project']
    write(store,path,{'notes':'B revised after confirmation'},dto['revision'])
    changed=service.discovery(identifier,NOW)
    with pytest.raises(Failure) as error:service.write(ADMIN,'POST',path+'/monitoring-requests',{'confirmed':True,'project':changed['project']},str(uuid.uuid4()),f'"rev-{changed["revision"]}"','retry',NOW)
    assert error.value.code=='CONFLICT' and error.value.status==409
    same=service.write(ADMIN,'POST',path+'/monitoring-requests',{'confirmed':True,'project':original},str(uuid.uuid4()),f'"rev-{changed["revision"]}"','same-original',NOW)
    assert same[0]==202 and same[1]['command_id']==command['command_id']
    with store.connect() as db:
        after=dict(db.execute('SELECT * FROM task_outbox').fetchone())
        assert {k:after[k] for k in before}==before
    assert service.discovery(identifier,NOW)['project']['notes']=='B revised after confirmation'

@pytest.mark.parametrize('stage',['audit','change'])
def test_patch_all_or_nothing(store,monkeypatch,stage):
    dto,path=resource(store);events=count(store,'public_changes')
    def fail(*args,**kwargs):raise RuntimeError('fixture transaction failure')
    monkeypatch.setattr(store,stage,fail)
    with pytest.raises(RuntimeError):write(store,path,{'notes':'must rollback'},dto['revision'])
    assert count(store,'operation_receipts')==0 and count(store,'public_changes')==events
    assert FormalService(store).discovery(dto['discovery_id'],NOW)['revision']==dto['revision']

def test_ttl_exact_microsecond_and_rollback_fence(store):
    dto,path=resource(store);first=micros(NOW);edge=first+TTL_US
    before=Decimal(edge-1)/1000000;at=Decimal(edge)/1000000
    assert FormalService(store).discovery(dto['discovery_id'],before)['discovery_id']==dto['discovery_id']
    with pytest.raises(Missing):FormalService(store).discovery(dto['discovery_id'],at)
    with pytest.raises(Missing):FormalService(Store(store.path)).discovery(dto['discovery_id'],NOW)
    result=store.cleanup(at)
    assert result['deleted']==1 and count(store,'discoveries')==0
    manifest=validate_bundle(result['backup']);assert manifest['expired_fences'][0]['discovery_id']==dto['discovery_id']
    with store.connect() as db:
        ledger=dict(db.execute('SELECT * FROM target_discovery_ledger').fetchone())
        assert set(ledger)=={'scope','platform','x_user_id','discovery_id','first_discovered_at_us','retired_at_us'}
        assert ledger['retired_at_us']==edge and 'hunter' not in canonical(ledger)

def test_last_moment_patch_does_not_extend_discovery_or_store_full_receipt(store):
    dto,path=resource(store);edge=NOW+604800;key=str(uuid.uuid4())
    result=write(store,path,{'notes':'expire this research'},dto['revision'],key,edge-2)
    store.cleanup(edge)
    assert write(store,path,{'notes':'expire this research'},dto['revision'],key,edge+1)==result
    with pytest.raises(Missing):write(store,path,{'rating':'B'},dto['revision']+1,now=edge+1)
    with client(store) as c:
        assert c.get(path,headers=headers()).status_code==404
        events=c.get('/internal/v1/events',headers=headers()).json()['data']['items']
        assert not any(x['type']=='hunter.discovery.updated' for x in events)
    with store.connect() as db:
        assert all('expire this research' not in r[0] for r in db.execute('SELECT response_json FROM operation_receipts'))
    store.cleanup(edge+604800)
    with pytest.raises(Missing):write(store,path,{'notes':'expire this research'},dto['revision'],key,edge+604800)

@pytest.mark.parametrize('failure',['backup','after_backup','before_commit'])
def test_backup_failure_never_deletes_but_clock_remains_expired(store,monkeypatch,failure):
    import hunterradar.retention as retention
    dto,path=resource(store)
    if failure=='backup':
        def fail(*args,**kwargs):raise OSError('fixture disk full')
        monkeypatch.setattr(retention,'backup_bundle',fail)
    with pytest.raises((OSError,RuntimeError)):store.cleanup(NOW+604800,failpoint=failure)
    assert count(store,'discoveries')==1 and count(store,'target_discovery_ledger')==1
    with pytest.raises(Missing):FormalService(store).discovery(dto['discovery_id'],NOW)
    assert count(store,'retention_runs')==0

def test_d4_retains_disabled_valid_history_and_exact_72h(store):
    # A whole-second reference keeps +1us representable at the store's precision.
    # Wall-clock .975 + 259200.000001 can instead become .9750009 and truncate.
    stamp=int(NOW)
    a=ready(store,'hunter1',user_id='101',now=stamp);ready(store,'hunter2',user_id='102',now=stamp)
    store.ingest_wss(event(at=stamp,received=stamp))
    store.patch(a['id'],a['version'],enabled=False,now=stamp+10)
    assert not store.ingest_wss(event(at=stamp+11,received=stamp+11))
    store.ingest_wss(event('hunter2',at=stamp+3600,received=stamp+3600))
    assert store.aggregate(stamp+259200)[0]['hunter_count']==2
    assert store.aggregate(stamp+259200.000001)==[]

def test_d4_resume_old_generation_and_rest_baseline(store):
    old=ready(store,'hunter1',user_id='101')
    off=store.patch(old['id'],old['version'],enabled=False,now=NOW+1)
    on=store.patch(off['id'],off['version'],enabled=True,now=NOW+2)
    store.apply_profile(on,'101','Fixture',5000,NOW+3);current=store.hunter(on['id']);store.establish_wss_baseline([current],NOW+4)
    assert not store.ingest_wss(event(at=NOW+5,received=NOW+5),generation=old['generation'])
    assert store.ingest_wss(event(at=NOW+5,received=NOW+5),generation=current['generation'])
    rest=ready(store,'hunter2',user_id='102',followers=4999)
    from hunterradar.parsers import Target
    targets=[Target('baseline','123','Baseline','')]
    assert store.apply_poll(rest,targets,NOW)['baseline']
    off=store.patch(rest['id'],rest['version'],enabled=False,now=NOW+1)
    assert store.apply_poll(rest,targets,NOW+2)['discarded']
    on=store.patch(off['id'],off['version'],enabled=True,now=NOW+3);store.apply_profile(on,'102','Fixture',4999,NOW+4)
    assert store.apply_poll(store.hunter(on['id']),targets,NOW+5)['new']==0

def test_d5_replay_rename_window_cleanup_restart_never_realerts(store):
    dto,path=resource(store)
    for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,at=NOW+259201,received=NOW+259201))
    assert count(store,'discoveries')==1
    assert FormalService(store).discovery(dto['discovery_id'],NOW+259201)['discovered_at']==dto['discovered_at']
    result=store.cleanup(NOW+604800)
    restarted=Store(store.path)
    for hunter in ('hunter1','hunter2'):
        assert not restarted.ingest_wss(event(hunter,target='renamed',target_id='999',at=NOW+604801,received=NOW+604801))
    assert count(store,'discoveries')==0 and count(store,'target_identities')==0
    for hunter in ('hunter1','hunter2'):assert restarted.ingest_wss(event(hunter,target='different',target_id='888',at=NOW+604802,received=NOW+604802))
    assert count(store,'discoveries')==1 and count(store,'target_discovery_ledger')==2
    with store.connect() as db:assert db.execute('SELECT count(*) FROM public_changes WHERE initial_publication=1').fetchone()[0]==1

def test_unknown_target_id_never_manufactures_durable_identity(store):
    ready(store,'hunter1',user_id='101');ready(store,'hunter2',user_id='102')
    for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,target_id=None))
    assert count(store,'discoveries')==0 and count(store,'target_discovery_ledger')==0

@pytest.mark.parametrize('posted',[False,True])
async def test_expired_confirmed_chain_and_late_receipt(store,tmp_path,posted):
    command,task=confirm(store)
    with store.connect(True) as db:db.execute('UPDATE task_outbox SET posted=?,status=? WHERE id=?',(int(posted),'unknown' if posted else 'pending',task['id']))
    result=store.cleanup(NOW+604800)
    with store.connect() as db:
        kept=dict(db.execute('SELECT * FROM task_outbox').fetchone())
        assert kept['id']==task['id'] and kept['event_id']==task['event_id'] and kept['target'] is None
        assert (kept['body']=='{}')==posted
    calls=[];canonical_id='prj_'+str(uuid.uuid4())
    async def receiver(request):
        calls.append(request.method)
        if request.method=='GET' and not posted:return httpx.Response(404)
        return httpx.Response(200,json={'data':{'event_id':task['event_id'],'command_id':task['command_id'],'project_id':canonical_id,'receipt_id':'fixture-receipt','accepted_at':'2026-10-16T00:00:00Z','duplicate':True}})
    settings=Settings(db=store.path,delivery_protocol='v2-event',project_url='http://127.0.0.1/internal/v1/ingest/hunter',project_token='p'*32)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as client:
        await Engine(settings,store,Providers(settings,store,client)).deliver(kept)
    assert calls==(['GET'] if posted else ['GET','POST'])
    assert count(store,'discoveries')==0
    with store.connect() as db:
        final=dict(db.execute('SELECT * FROM task_outbox').fetchone())
        assert final['project_id']==canonical_id and json.loads(final['receipt_json'])['accepted_at']=='2026-10-16T00:00:00Z'
    store.cleanup(NOW+604801)
    with store.connect() as db:assert db.execute('SELECT body FROM task_outbox').fetchone()[0]=='{}'
    restored_path=tmp_path.resolve()/'restored'/'hunter.db'
    restore_bundle(result['backup'],restored_path,current=store.path)
    recovered=Store(restored_path)
    assert count(recovered,'discoveries')==0
    with recovered.connect() as db:
        original=dict(db.execute('SELECT * FROM task_outbox').fetchone())
        assert original['posted']==1 and original['project_id']==canonical_id and original['body']=='{}'
    assert FormalService(recovered).command(command['command_id'],'fixture')['project_id']==canonical_id

def test_verified_restore_union_and_raw_backup_fail_closed(store,tmp_path):
    dto,path=resource(store)
    bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW))
    write(store,path,{'rating':'S'},dto['revision'])
    for hunter in ('hunter1','hunter2'):store.ingest_wss(event(hunter,target='later',target_id='888',at=NOW+1,received=NOW+1))
    dest=tmp_path.resolve()/'restored'/'hunter.db'
    with pytest.raises(ValueError,match='latest_recovery'):restore_bundle(bundle,dest,current=None)
    assert not dest.exists()
    restore_bundle(bundle,dest,current=store.path);restored=Store(dest)
    assert count(restored,'target_discovery_ledger')==2
    assert FormalService(restored).discovery(dto['discovery_id'],NOW)['revision']>dto['revision']+1
    with pytest.raises(Conflict,match='requires_recovery'):restored.ingest_wss(event(target='later',target_id='888',at=NOW+2,received=NOW+2))
    with pytest.raises(ValueError):restore_bundle(store.path.parent,tmp_path.resolve()/'raw'/'hunter.db',current=store.path)

def test_restore_never_reuses_discovery_or_command_sse_sequence(store,tmp_path):
    dto,path=resource(store)
    bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW))
    for i in range(5):
        dto=FormalService(store).discovery(dto['discovery_id'],NOW)
        write(store,path,{'notes':'Synthetic sequence '+str(i)},dto['revision'])
    with store.connect(True) as db:
        db.execute('INSERT INTO public_changes(type,entity_id,data,received_at) VALUES(?,?,?,?)',('command.updated','cmd_'+str(uuid.uuid4()),'{}',NOW))
        floor=db.execute("SELECT seq FROM sqlite_sequence WHERE name='public_changes'").fetchone()[0]
        db.execute('DELETE FROM public_changes') # Assigned sequence exists only in sqlite_sequence.
    dest=tmp_path.resolve()/'restored'/'hunter.db';restore_bundle(bundle,dest,current=store.path);restored=Store(dest)
    for hunter in ('hunter1','hunter2'):restored.ingest_wss(event(hunter,target='novel',target_id='777',at=NOW+1,received=NOW+1))
    with client(restored) as c:
        events=c.get('/internal/v1/events?after='+str(floor),headers=headers()).json()['data']['items']
    assert len(events)==1 and events[0]['sequence']>floor and events[0]['type']=='hunter.discovery.updated'

@pytest.mark.parametrize('source',['wss','rest'])
def test_clock_forward_then_rollback_never_burns_first_target_alert(store,source):
    from hunterradar.parsers import Target
    hunters=[ready(store,'hunter'+str(i),user_id=str(100+i),followers=5000 if source=='wss' else 4999) for i in (1,2)]
    if source=='rest':
        for row in hunters:store.apply_poll(row,[],NOW)
    store.retention_clock(NOW+4*86400)
    for row in hunters:
        if source=='wss':assert not store.ingest_wss(event(row['username'],at=NOW+1,received=NOW+1))
        else:assert store.apply_poll(row,[Target('project1','999','Synthetic','')],NOW+1)['new']==0
    assert count(store,'target_discovery_ledger')==0 and store.aggregate(NOW+1)==[]
    assert FormalService(store).page('signals',{},NOW+1)['items']==[]
    future=NOW+4*86400+1
    for row in hunters:
        if source=='wss':store.ingest_wss(event(row['username'],target='fresh',target_id='888',at=future,received=future))
        else:store.apply_poll(row,[Target('fresh','888','Fresh','')],future)
    items=FormalService(store).page('signals',{},NOW+1)['items']
    assert len(items)==1 and items[0]['signal_count']==2 and items[0]['x_user_id']=='888'
    assert store.aggregate(NOW+1)[0]['hunter_count']==2

def test_restore_rejects_bundle_itself_as_claimed_current(store,tmp_path):
    resource(store);bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW))
    destination=tmp_path.resolve()/'invalid'/'hunter.db'
    with pytest.raises(ValueError,match='not_backup'):restore_bundle(bundle,destination,current=bundle/'hunter.db')
    assert not destination.exists()

@pytest.mark.parametrize('phase',['after_copy','before_merge_commit','after_merge_commit','after_reservation','after_publish'])
def test_restore_publication_boundaries_fail_closed(store,tmp_path,phase):
    resource(store);bundle,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW));destination=tmp_path.resolve()/'destination'/'hunter.db'
    def stop(at):
        if at==phase:raise RuntimeError('fixture restore boundary')
    with pytest.raises(RuntimeError):restore_bundle(bundle,destination,current=store.path,progress=stop)
    if phase=='after_publish':assert Store(destination)
    else:
        with pytest.raises(ValueError):Store(destination)
    for candidate in destination.parent.glob('.hunter-restore-*.tmp'):
        with pytest.raises(ValueError,match='must_be_named'):Store(candidate)

def test_backup_tamper_and_backup_count_age_limits(store):
    dto,path=resource(store)
    folders=[]
    for i in range(5):
        folder,_=backup_bundle(store.path,kind='retention',clock_us=micros(NOW+i));folders.append(folder)
    from hunterradar.retention import prune_bundles
    prune_bundles(store.path,micros(NOW+5))
    assert sum(p.exists() for p in folders)==3
    manifest=folders[-1]/'manifest.json';data=json.loads(manifest.read_text());data['commands']=[{'id':'tampered'}];manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='commands_mismatch'):validate_bundle(folders[-1])
    # Keep only a small failure receipt, never expired corrupt copies containing business content.
    prune_bundles(store.path,micros(NOW+4+172800))
    assert [p for p in folders if p.exists()]==[]
    assert list((store.path.parent/'recovery').glob('failed-*.json'))

def test_real_online_backup_timeout_does_not_delete(store,monkeypatch):
    import hunterradar.retention as retention
    dto,path=resource(store);monkeypatch.setattr(retention,'BACKUP_DEADLINE_SECONDS',0)
    with pytest.raises(TimeoutError,match='backup_deadline'):store.cleanup(NOW+604800)
    assert count(store,'discoveries')==1 and count(store,'retention_runs')==0
    with pytest.raises(Missing):FormalService(store).discovery(dto['discovery_id'],NOW)

def old_schema3(folder,*,stable=True):
    path=folder/'hunter.db'
    with sqlite3.connect(path) as db:
        for version in (1,2,3):statements(db,(SQL_ROOT/FILES[version]).read_text())
        db.execute(f'PRAGMA application_id={APP_ID}');db.execute('PRAGMA user_version=3')
        db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'hunter')")
        db.execute('CREATE TABLE _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL) STRICT')
        for version in (1,2,3):
            db.execute('INSERT INTO _schema_migrations(version,name,applied_at) VALUES(?,?,?)',(version,NAMES[version],'fixture'))
            db.execute('INSERT INTO _migration_checksums(version,sha256) VALUES(?,?)',(version,checksums()[version]))
        db.execute('INSERT INTO _hunter_migrations(version,checksum,applied_at) VALUES(2,?,?)',(checksums()[2],'fixture'))
        db.execute('INSERT INTO discoveries(target,first_discovered_at,discovery_id,notes) VALUES(?,?,?,?)',('legacy',NOW,'dsc_'+str(uuid.uuid4()),'retained research'))
        db.execute('INSERT INTO target_identities(entity_key,anchor,x_user_id,current_handle,updated_at) VALUES(?,?,?,?,?)',('tgt_fixture','legacy','999' if stable else None,'legacy',NOW))
        db.execute('INSERT INTO target_aliases(x_handle,entity_key) VALUES(?,?)',('legacy','tgt_fixture'))
        db.execute("INSERT INTO state(key,value) VALUES('cursor_secret','\"fixture\"')")
    path.chmod(0o600)
    return path

@pytest.mark.parametrize('stable',[False,True])
def test_schema3_upgrade_backup_or_ambiguous_identity_rollback(tmp_path,stable):
    path=old_schema3(tmp_path.resolve(),stable=stable)
    if stable:
        migrate(path);migrate(path)
        assert count(Store(path),'target_discovery_ledger')==1
        assert Store(path).discovery('legacy')['notes']=='retained research'
    else:
        with pytest.raises(ValueError,match='identity_review_required'):migrate(path)
        with sqlite3.connect(path) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==3
            assert db.execute('SELECT notes FROM discoveries').fetchone()[0]=='retained research'
            assert db.execute("SELECT 1 FROM sqlite_master WHERE name='target_discovery_ledger'").fetchone() is None
    bundles=list((path.parent/'recovery').glob('migration-*'));assert len(bundles)==1
    assert validate_bundle(bundles[0])['schema']['3']=='hunter_b4_protocol'

async def test_background_cleanup_independent_of_website(store,monkeypatch):
    calls=[]
    engine=Engine(Settings(db=store.path),store)
    def local_cleanup():calls.append(True);engine.stop.set();return {'deleted':0}
    monkeypatch.setattr(store,'cleanup',local_cleanup)
    await engine.retention_loop();await engine.providers.close()
    assert calls==[True] and store.states()['retention_error'] is None

def test_cleanup_restore_only_open_hunter_files_and_never_attach(store,tmp_path,monkeypatch):
    resource(store);sentinels={name:tmp_path/(name+'-sentinel') for name in ('projects','tracking','auth')}
    for name,path in sentinels.items():path.write_text('Synthetic untouched '+name)
    before={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sentinels.items()}
    opened=[];attaches=[];original=sqlite3.connect
    def connector(path,*args,**kwargs):
        opened.append(str(path));connection=original(path,*args,**kwargs)
        def authorize(action,*details):
            if action==sqlite3.SQLITE_ATTACH:attaches.append(details);return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorize);return connection
    monkeypatch.setattr(sqlite3,'connect',connector)
    result=store.cleanup(NOW+604800)
    restore_bundle(result['backup'],tmp_path.resolve()/'restored'/'hunter.db',current=store.path)
    import re
    from urllib.parse import unquote,urlsplit
    for value in opened:
        path=Path(unquote(urlsplit(value).path) if value.startswith('file:') else value)
        assert path.is_relative_to(tmp_path.resolve())
        assert path.name=='hunter.db' or re.fullmatch(r'\.hunter-restore-[a-f0-9]{32}\.tmp',path.name)
    assert opened and attaches==[]
    assert before=={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sentinels.items()}

def test_inadmissible_restore_staging_also_has_finite_retention(tmp_path):
    from hunterradar.retention import prune_restore_staging
    temp=tmp_path/('.hunter-restore-'+uuid.uuid4().hex+'.tmp');temp.write_text('Synthetic interrupted restore');temp.chmod(0o600)
    sidecar=Path(str(temp)+'-wal');sidecar.write_text('Synthetic');sidecar.chmod(0o600)
    future=micros(max(temp.stat().st_mtime,getattr(temp.stat(),'st_birthtime',0))+172800)
    prune_restore_staging(tmp_path,future)
    assert not temp.exists() and not sidecar.exists()

def test_formal_settings_ignore_cwd_env_and_reject_external_switch(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'.env').write_text('OPENNEWS_TOKEN=synthetic-do-not-load\nHUNTER_EXTERNAL_IO_ENABLED=1\n')
    for name in ('OPENNEWS_TOKEN','TWITTERAPI_IO_API_KEY','HUNTER_EXTERNAL_IO_ENABLED','HUNTER_REQUIRE_EXTERNAL_IO_DISABLED','HUNTER_SECRETS_FILE'):monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('HUNTER_V2_MODE','1')
    cfg=Settings.load();assert cfg.token_6551=='' and not cfg.external_io_enabled and cfg.require_external_io_disabled
    monkeypatch.setenv('HUNTER_EXTERNAL_IO_ENABLED','1')
    with pytest.raises(ValueError,match='collection_forbidden'):Settings.load()

def test_readiness_reports_no_real_source_and_internal_delivery_separately(store):
    with client(store) as c:
        body=c.get('/health/ready').json()['data']
        assert body['source_status']=='未连接真实来源' and body['external_io_enabled'] is False
        assert body['schema_version']==LATEST_VERSION and body['project_delivery_enabled'] is False
    cfg=Settings(v2_mode=True,external_io_enabled=False,require_external_io_disabled=True,project_delivery_enabled=True,project_url='http://127.0.0.1/internal/v1/ingest/hunter',project_token='x'*32,delivery_protocol='v2-event')
    assert cfg.project_delivery_enabled and not cfg.external_io_enabled

def test_location_accepts_disappearing_sidecars_with_one_lstat(store,monkeypatch):
    from hunterradar.migration import location
    original=Path.lstat;calls={}
    def observe(path,*args,**kwargs):
        calls[path]=calls.get(path,0)+1
        if path.name in ('hunter.db-wal','hunter.db-shm'):raise FileNotFoundError('SQLite removed sidecar')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',observe)
    assert location(store.path,require_exists=True)==store.path
    assert calls[Path(str(store.path)+'-wal')]==1 and calls[Path(str(store.path)+'-shm')]==1

def test_location_still_refuses_symlinked_sidecar(store,tmp_path):
    from hunterradar.migration import location
    target=tmp_path/'sentinel';target.write_text('Synthetic');target.chmod(0o600)
    sidecar=Path(str(store.path)+'-wal')
    if sidecar.exists():sidecar.unlink()
    sidecar.symlink_to(target)
    with pytest.raises(ValueError,match='symlinked'):location(store.path,require_exists=True)
    assert target.read_text()=='Synthetic'

def test_ignore_hides_discovery_from_default_list_only(store):
    dto,path=resource(store);svc=FormalService(store)
    before=[i['discovery_id'] for i in svc.page('signals',{},NOW)['items']]
    assert dto['discovery_id'] in before
    status,_,_=write(store,path,{'ignored':True},dto['revision'])
    assert status==200
    current=FormalService(Store(store.path)).discovery(dto['discovery_id'],NOW)
    assert current['review_state']=='ignored' and current['revision']==dto['revision']+1
    assert dto['discovery_id'] not in [i['discovery_id'] for i in svc.page('signals',{},NOW)['items']]
    assert dto['discovery_id'] in [i['discovery_id'] for i in svc.page('signals',{'review_state':'ignored'},NOW)['items']]
    with pytest.raises(Exception):write(store,path,{'ignored':'yes'},current['revision'])
