import sys
"""Frozen c4de Tracking wire -> Projects metadata inbox; no worker DB or publisher."""
import concurrent.futures
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import uuid

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from projects_service.db import DomainError
from projects_service.ipc import IpcConfig, create_ipc_app
from projects_service.service import Service
from projects_service import tracking_observations as obs
from test_b2_domain import USER, call, create, domain, event as hunter_event, uid

ROOT=Path(__file__).resolve().parents[4]
EXAMPLE=json.loads((ROOT/'modules/projects/protocols/tracking-observations-v1.json').read_text())['examples']['event']

def event(project_id,*,event_type=obs.CREATED,kind='original',source='wss',subscription=None):
    value=copy.deepcopy(EXAMPLE);p=value['payload'];value['event_id']=uid('evt_')
    value['project_id']=p['project_id']=project_id
    p['subscription_id']=subscription or p['subscription_id'];p['tweet_kind']=kind;p['source']=source
    p['is_live_new']=event_type==obs.CREATED;p['replay']=not p['is_live_new'];value['event_type']=event_type
    p['activity_id']='act_'+str(uuid.uuid5(obs.NAMESPACE,json.dumps(['ikun-main',p['subscription_id'],p['tweet_id']],separators=(',',':'))))
    value['correlation_id']=p['activity_id'];return value

def hashed(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def ingest(service,value,expected=...):
    query={} if expected is None else {'expected_hash':hashed(value) if expected is ... else expected}
    return call(service,'ingest',principal=None,source='tracking',contract=obs.CONTRACT,body=value,query=query)[1]
def receipt(service,value,expected=...):
    query={} if expected is None else {'expected_hash':hashed(value) if expected is ... else expected}
    return call(service,'receipt',principal=None,source='tracking',contract=obs.CONTRACT,target=value['event_id'],query=query)[1]

@pytest.mark.parametrize('event_type,kind,source',[
    (obs.CREATED,'original','wss'),(obs.CREATED,'quote','wss'),
    *[(obs.UPDATED,kind,source) for kind,source in [('original','wss'),('quote','rest'),('unknown','wss'),('reply','rest'),('repost','wss')]],
])
def test_exact_frozen_events_and_visibility_corrections(domain,event_type,kind,source):
    p=create(domain);value=event(p['project_id'],event_type=event_type,kind=kind,source=source)
    result=ingest(domain,value)
    assert set(result)=={'event_id','project_id','receipt_id','accepted_at','duplicate','command_id'}
    assert result['project_id']==p['project_id'] and result['event_id']==value['event_id'] and not result['duplicate'] and result['command_id'] is None
    assert receipt(domain,value)=={**result,'duplicate':True}

def test_metadata_only_and_rating_catalog_no_business_change(domain):
    p=create(domain);value=event(p['project_id']);value['payload']['text']='BODY_MUST_NOT_PERSIST_观察';value['payload']['project_name']='NOT_THE_CANONICAL_NAME'
    before=call(domain,'get',target=p['project_id'])[1]
    catalog=call(domain,'ratings',contract='tracking-ratings-v1',body={'project_ids':[],'expected_catalog_version':None})[1]['catalog_version']
    tables=['projects','audit_log','operation_receipts','tracking_outbox','project_changes','project_milestones','project_completions']
    with domain.db.connect() as con:counts={name:con.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in tables}
    result=ingest(domain,value)
    with domain.db.connect() as con:
        assert counts=={name:con.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in tables}
        row=con.execute("SELECT * FROM event_inbox WHERE source='tracking'").fetchone();assert row['body_hash']==hashed(value)
        alias=con.execute("SELECT * FROM project_sources WHERE source='tracking'").fetchone()
        assert alias['external_id']=='observations-v1:subscription:'+value['payload']['subscription_id'] and alias['project_id']==p['project_id']
        dump='\n'.join(con.iterdump());assert value['payload']['text'] not in dump and value['payload']['project_name'] not in dump
    assert call(domain,'get',target=p['project_id'])[1]==before and result['accepted_at']!=value['received_at']
    assert call(domain,'ratings',contract='tracking-ratings-v1',body={'project_ids':[],'expected_catalog_version':catalog})[1]['catalog_version']==catalog

def test_replay_key_order_hash_conflict_and_original_acceptance_time(domain):
    p=create(domain);value=event(p['project_id']);first=ingest(domain,value)
    reordered=dict(reversed(list(value.items())));reordered['payload']=dict(reversed(list(value['payload'].items())))
    assert ingest(domain,reordered)=={**first,'duplicate':True}
    changed=copy.deepcopy(value);changed['payload']['text']+='different'
    with pytest.raises(DomainError) as exc:ingest(domain,changed)
    assert exc.value.status==409 and exc.value.code=='CONFLICT'
    assert receipt(domain,value)['accepted_at']==first['accepted_at']
    with domain.db.connect() as con:assert con.execute("SELECT COUNT(*) FROM event_inbox WHERE source='tracking'").fetchone()[0]==1

def test_time_representation_is_not_normalized_before_hash(domain):
    p=create(domain);value=event(p['project_id']);ingest(domain,value)
    changed=copy.deepcopy(value);changed['received_at']=changed['payload']['received_at']=value['received_at'].replace('.000Z','.0Z')
    assert hashed(changed)!=hashed(value)
    with pytest.raises(DomainError) as exc:ingest(domain,changed)
    assert exc.value.status==409

@pytest.mark.parametrize('bad_hash',['bad','A'*64,None,1,'0'*63])
def test_invalid_expected_hash_does_not_write(domain,bad_hash):
    p=create(domain);value=event(p['project_id'])
    with pytest.raises(DomainError) as exc:call(domain,'ingest',principal=None,source='tracking',contract=obs.CONTRACT,body=value,query={'expected_hash':bad_hash})
    assert exc.value.status==422
    with domain.db.connect() as con:assert con.execute('SELECT COUNT(*) FROM event_inbox').fetchone()[0]==0

def test_hash_checks_on_both_ingest_and_receipt(domain):
    p=create(domain);value=event(p['project_id'])
    with pytest.raises(DomainError) as exc:ingest(domain,value,'0'*64)
    assert exc.value.status==409
    first=ingest(domain,value)
    with pytest.raises(DomainError) as exc:receipt(domain,value,'0'*64)
    assert exc.value.status==409 and receipt(domain,value)['receipt_id']==first['receipt_id']

def test_concurrent_replay_and_new_event_do_not_duplicate_identity(domain):
    p=create(domain);value=event(p['project_id'])
    with concurrent.futures.ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda _:ingest(domain,value),range(12)))
    assert len({row['receipt_id'] for row in results})==1 and sum(not row['duplicate'] for row in results)==1
    updated=event(p['project_id'],event_type=obs.UPDATED,source='rest');ingest(domain,updated)
    with domain.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM project_sources WHERE source='tracking'").fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM event_inbox WHERE source='tracking'").fetchone()[0]==2

def test_subscription_conflict_does_not_rebind(domain):
    a=create(domain);b=create(domain);first=event(a['project_id']);ingest(domain,first)
    wrong=event(b['project_id'])
    with pytest.raises(DomainError) as exc:ingest(domain,wrong)
    assert exc.value.status==409
    assert receipt(domain,first)['project_id']==a['project_id']
    with pytest.raises(DomainError) as exc:receipt(domain,wrong)
    assert exc.value.status==404

def test_transaction_failure_after_alias_rolls_back_inbox_and_mapping(domain,monkeypatch):
    p=create(domain);value=event(p['project_id']);original=domain.db.connect
    class Fault:
        def __init__(self,con):self.con=con
        def __getattr__(self,key):return getattr(self.con,key)
        def execute(self,sql,*args):
            if sql.startswith('INSERT INTO event_inbox'):raise sqlite3.OperationalError('synthetic disk failure')
            return self.con.execute(sql,*args)
    @contextmanager
    def connect():
        with original() as con:yield Fault(con)
    monkeypatch.setattr(domain.db,'connect',connect)
    with pytest.raises(sqlite3.OperationalError):ingest(domain,value)
    with original() as con:
        assert con.execute("SELECT COUNT(*) FROM event_inbox WHERE source='tracking'").fetchone()[0]==0
        assert con.execute("SELECT COUNT(*) FROM project_sources WHERE source='tracking'").fetchone()[0]==0

@pytest.mark.parametrize('membership,grade',[('hidden','A'),('removed','S'),('active','C'),('active','D'),('active',None)])
def test_observation_does_not_add_or_upgrade_projects(domain,membership,grade):
    p=create(domain,rating=grade)
    if membership!='active':
        with domain.db.transaction() as con:con.execute('UPDATE projects SET home_membership=? WHERE id=?',(membership,p['project_id']))
    before=call(domain,'get',target=p['project_id'])[1];ingest(domain,event(p['project_id']))
    assert call(domain,'get',target=p['project_id'])[1]==before

@pytest.mark.parametrize('path,value',[
    ('schema_version',True),('schema_version',1.0),('schema_version',2),('event_id','evt_bad'),('event_type','tracking.tweet'),
    ('project_id',None),('correlation_id','act_bad'),('occurred_at','2026-02-30T00:00:00Z'),('received_at','2026-01-01T00:00:00+00:00'),
    ('payload.activity_id','act_550e8400-e29b-41d4-a716-446655440000'),('payload.subscription_id','sub_bad'),('payload.project_id','prj_bad'),
    ('payload.tweet_id','-1'),('payload.x_handle','@wrong'),('payload.url','https://private.invalid/secret'),
    ('payload.project_name',''),('payload.text','x'*20001),('payload.text','\ud800'),('payload.generation',True),('payload.generation',0),('payload.generation',2**63),
    ('payload.replay',True),('payload.is_live_new',False),('payload.tweet_kind','unknown'),('payload.extra',None),('expired',True),
])
def test_strict_actual_wire_rejects_bad_fields(domain,path,value):
    p=create(domain);body=event(p['project_id']);target=body;parts=path.split('.')
    for part in parts[:-1]:target=target[part]
    target[parts[-1]]=value
    with pytest.raises(ValidationError):ingest(domain,body,expected=None)

def test_scope_source_and_unrelated_canonical_are_not_imported(domain):
    p=create(domain);body=event(p['project_id'])
    for key,value in [('tenant_id','foreign'),('source','hunter')]:
        bad=copy.deepcopy(body);bad[key]=value
        with pytest.raises(DomainError) as exc:ingest(domain,bad,expected=None)
        assert exc.value.status==403
    missing=event(uid('prj_'))
    with pytest.raises(DomainError) as exc:ingest(domain,missing)
    assert exc.value.status==404
    with domain.db.transaction() as con:con.execute("UPDATE projects SET tenant_id='foreign' WHERE id=?",(p['project_id'],))
    with pytest.raises(DomainError) as exc:ingest(domain,body)
    assert exc.value.status==404

def test_scrubbed_event_requires_get_and_absent_receipt_remains_unknown(domain):
    p=create(domain);accepted=event(p['project_id']);first=ingest(domain,accepted)
    unseen=event(p['project_id'],event_type=obs.UPDATED)
    for body in [accepted,unseen]:
        # Exact minimal-field extraction from c4de retention.purge, not a reconstructed body.
        scrub={key:body[key] for key in ('schema_version','event_id','source','event_type','tenant_id','project_id','correlation_id','received_at')};scrub['expired']=True
        with pytest.raises(ValidationError):ingest(domain,scrub,expected=None)
    assert receipt(domain,accepted)['receipt_id']==first['receipt_id']
    with pytest.raises(DomainError) as exc:receipt(domain,unseen)
    assert exc.value.status==404 and exc.value.code=='NOT_FOUND'
    # No new inbox/ACK was manufactured for the expired, never-receipted event.
    with domain.db.connect() as con:assert con.execute("SELECT COUNT(*) FROM event_inbox WHERE source='tracking'").fetchone()[0]==1

@pytest.mark.parametrize('text',['\U0001f600'*20000,'\u0001'*20000])
def test_maximum_text_and_int64_preserve_hash_without_body_storage(domain,text):
    p=create(domain);value=event(p['project_id']);value['payload']['text']=text;value['payload']['generation']=9223372036854775807
    first=ingest(domain,value);assert receipt(Service(domain.db),value)['receipt_id']==first['receipt_id']
    with domain.db.connect() as con:assert con.execute("SELECT body_hash FROM event_inbox WHERE source='tracking'").fetchone()[0]==hashed(value)

def test_private_handler_auth_error_envelopes_and_no_foreign_store(domain,monkeypatch):
    p=create(domain);value=event(p['project_id']);config=IpcConfig(str(domain.db.path),'i'*64,'f'*40);original=sqlite3.connect;opened=[]
    def guarded(path,*args,**kwargs):
        opened.append(str(path));assert 'projects.db' in str(path);return original(path,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',guarded)
    wire={'operation':'ingest','source':'tracking','contract':obs.CONTRACT,'request_id':uid(),'body':value,'query':{'expected_hash':hashed(value)}}
    with TestClient(create_ipc_app(config),raise_server_exceptions=False) as client:
        headers={'authorization':'Bearer '+config.token,'x-ikun-build-sha':config.build_sha}
        assert client.post('/v1/rpc',json=wire).status_code==401
        assert client.post('/v1/rpc',headers={**headers,'x-ikun-build-sha':'a'*40},json=wire).status_code==403
        assert client.post('/v1/rpc',headers=headers,json={**wire,'principal':USER}).status_code==403
        response=client.post('/v1/rpc',headers=headers,json=wire);assert response.status_code==200
        assert response.json()['request_id']==response.headers['x-request-id'] and opened

def test_real_tracking_route_and_http_reconcile(tmp_path):
    from projects_service.migration import FormalDatabase
    data=tmp_path/'data';db=FormalDatabase(data/'projects/projects.db');db.migrate();service=Service(db);p=create(service);other=create(service,name='unrelated canonical')
    samples={}
    for label in ['base','lost_ack','unseen_expired','updated','max_emoji','max_control','fraction_schema','fraction_generation','storage_fault']:
        sample=event(p['project_id'],event_type=obs.UPDATED if label=='updated' else obs.CREATED,kind='unknown' if label=='updated' else 'original')
        if label=='storage_fault':sample=event(p['project_id'],subscription=uid('sub_'))
        if label in ('max_emoji','max_control'):
            char='\U0001f600' if label=='max_emoji' else '\u0001';sample['payload']['text']=char*20000;sample['payload']['project_name']=char*120
            sample['payload']['generation']=9223372036854775807
            sample['received_at']=sample['payload']['received_at']='2026-10-16T00:00:01.123456789Z'
        if label=='fraction_schema':sample['schema_version']=1.0
        if label=='fraction_generation':sample['payload']['generation']=1.0
        samples[label]={'raw':json.dumps(sample,sort_keys=True,separators=(',',':'),ensure_ascii=False),'sha256':hashed(sample),'event_id':sample['event_id']}
    failed=json.loads(samples['storage_fault']['raw'])
    with db.transaction() as con:
        con.execute("CREATE TRIGGER injected_inbox_failure BEFORE INSERT ON event_inbox WHEN NEW.event_id='"+failed['event_id']+"' BEGIN SELECT RAISE(ABORT,'synthetic inbox failure'); END")
    fixture=tmp_path/'events.json';fixture.write_text(json.dumps({'project':p,'other_project':other,'event':event(p['project_id']),
        'hunter_event':hunter_event(name='hunter regression control'),'cases':samples},ensure_ascii=False))
    import os
    env={**os.environ,'DATA_ROOT':str(data),'PROJECTS_PYTHON':sys.executable,
         'B2_BUILD_SHA':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'TI_FIXTURE':str(fixture)}
    node=shutil.which('node')
    result=subprocess.run([node,'--import',str(ROOT/'node_modules/tsx/dist/loader.mjs'),
        '--test',str(ROOT/'modules/projects/integration/tests/tracking-ingest.test.mjs')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=40)
    (tmp_path/'tracking-node.tap').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert call(service,'get',target=p['project_id'])[1]==p
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM event_inbox WHERE event_id=?',(failed['event_id'],)).fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM project_sources WHERE external_id=?',('observations-v1:subscription:'+failed['payload']['subscription_id'],)).fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM tracking_outbox').fetchone()[0]==1  # Original Hunter command only.
    marker=EXAMPLE['payload']['text'].encode()
    for path in db.path.parent.glob('projects.db*'):
        assert marker not in path.read_bytes()  # Includes WAL if still present.
