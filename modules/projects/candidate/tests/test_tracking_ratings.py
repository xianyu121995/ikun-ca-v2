"""C03 exact wire and real Projects storage/IPC; no Tracking or Hunter database."""
import concurrent.futures
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import shutil
import subprocess

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from projects_service.db import DomainError, project_path
from projects_service.ipc import IpcConfig, create_ipc_app
from projects_service.migration import FormalDatabase
from projects_service.service import Service
from projects_service.transport import Rpc
from test_b2_domain import ADMIN, USER, FIELDS, call, create, domain, uid

CONTRACT='tracking-ratings-v1'
ID='prj_550e8400-e29b-41d4-a716-446655440000'

def lookup(service,ids=(),expected=None,principal=USER):
    return call(service,'ratings',contract=CONTRACT,principal=principal,
                body={'project_ids':list(ids),'expected_catalog_version':expected})[1]

@pytest.mark.parametrize('grade',['S','A','B','C','D',None])
def test_exact_projection_and_all_underlying_ratings(domain,grade):
    p=create(domain,rating=grade,notes='private-to-project-record',description='not a rating field')
    data=lookup(domain,[p['project_id'],ID]);assert set(data)=={'contract','catalog_version','checked_at','items'}
    assert data['contract']==CONTRACT and 1<=len(data['catalog_version'])<=128
    checked=datetime.fromisoformat(data['checked_at'].replace('Z','+00:00'))
    assert data['checked_at'].endswith('Z') and abs((datetime.now(timezone.utc)-checked).total_seconds())<2
    assert data['items']==[{'project_id':p['project_id'],'state':'found','rating':grade,'revision':1},
                          {'project_id':ID,'state':'missing','rating':None,'revision':None}]

@pytest.mark.parametrize('size',[0,1,200])
def test_zero_through_maximum_batch_is_complete(domain,size):
    ids=[uid('prj_') for _ in range(size)];page=lookup(domain,ids)
    assert [item['project_id'] for item in page['items']]==ids
    assert all(item['state']=='missing' and item['rating'] is item['revision'] is None for item in page['items'])
    assert lookup(domain,expected=page['catalog_version'])['catalog_version']==page['catalog_version']

@pytest.mark.parametrize('body',[
    {},{'project_ids':[]},{'expected_catalog_version':None},
    {'project_ids':'not-a-list','expected_catalog_version':None},
    {'project_ids':[ID,ID],'expected_catalog_version':None},
    {'project_ids':['prj_bad'],'expected_catalog_version':None},
    {'project_ids':['prj_550e8400-e29b-11d4-a716-446655440000'],'expected_catalog_version':None},
    {'project_ids':[uid('prj_') for _ in range(201)],'expected_catalog_version':None},
    *[{'project_ids':[],'expected_catalog_version':v} for v in (0,True,'','x'*129)],
    {'project_ids':[],'expected_catalog_version':None,'rating':'S'},
])
def test_request_is_strict_and_does_not_turn_bad_version_into_first_page(body):
    with pytest.raises(ValidationError):Rpc(operation='ratings',contract=CONTRACT,principal=USER,request_id=uid(),body=body)

@pytest.mark.parametrize('extra',[{'query':{}},{'target':ID},{'source':'tracking'},{'if_match':'"rev-1"'},{'idempotency_key':uid()}])
def test_no_generic_query_or_write_fields(extra):
    with pytest.raises(ValidationError):Rpc(operation='ratings',contract=CONTRACT,principal=USER,request_id=uid(),
        body={'project_ids':[],'expected_catalog_version':None},**extra)

@pytest.mark.parametrize('operation,contract',[('ratings','phase2-v1.0.0'),('ratings','projects-home-v1'),('get',CONTRACT),('create',CONTRACT)])
def test_new_contract_cannot_select_old_operations(operation,contract):
    with pytest.raises(ValidationError):Rpc(operation=operation,contract=contract,principal=ADMIN,request_id=uid(),body={})

@pytest.mark.parametrize('actor',[None,USER,ADMIN])
def test_read_authorization_is_required_for_both_existing_roles(domain,actor):
    if actor is None:
        with pytest.raises(DomainError) as exc:lookup(domain,principal=actor)
        assert exc.value.status==401
    else:assert lookup(domain,principal=actor)['items']==[]

def test_global_catalog_cross_batch_change_and_existence(domain):
    a=create(domain);b=create(domain);version=lookup(domain)['catalog_version']
    assert lookup(domain,[a['project_id']],version)['items'][0]['rating']=='A'
    call(domain,'patch',target=b['project_id'],body={'rating':'S'},if_match='"rev-1"',idempotency_key=uid())
    for ids in ([],[b['project_id']]):
        with pytest.raises(DomainError) as exc:lookup(domain,ids,version)
        assert exc.value.status==409 and exc.value.code=='VERSION_CONFLICT'
    changed=lookup(domain,[b['project_id']]);assert changed['catalog_version']!=version
    assert changed['items'][0]['rating']=='S' and changed['items'][0]['revision']==2
    create(domain,name='new canonical')
    with pytest.raises(DomainError):lookup(domain,expected=changed['catalog_version'])

def test_201_projects_across_two_concurrent_batches_have_one_catalog(domain):
    grades=['S','A','B','C','D',None]
    projects=[create(domain,name=f'catalog {i:03}',rating=grades[i%6]) for i in range(201)]
    ids=[p['project_id'] for p in projects];version=lookup(domain)['catalog_version']
    with concurrent.futures.ThreadPoolExecutor(2) as pool:pages=list(pool.map(lambda batch:lookup(domain,batch,version),[ids[:200],ids[200:]]))
    assert all(page['catalog_version']==version for page in pages)
    items=[item for page in pages for item in page['items']]
    assert [item['project_id'] for item in items]==ids and [item['rating'] for item in items]==[p['rating'] for p in projects]

def test_c02_completion_restore_and_membership_keep_rating_and_identity(domain):
    p=create(domain,rating='S',progress_percent=37);target=p['project_id'];version=lookup(domain)['catalog_version']
    for operation,revision,body in [('completion',1,{}),('restore',2,{}),('delete',3,{})]:
        call(domain,operation,target=target,body=body,if_match=f'"rev-{revision}"',idempotency_key=uid())
        current=lookup(domain,[target]);assert current['items']==[{'project_id':target,'state':'found','rating':'S','revision':revision+1}]
        assert current['catalog_version']!=version;version=current['catalog_version']
    stored=call(domain,'get',target=target)[1]
    assert stored['home_membership']=='removed' and stored['progress_stage']=='researching' and stored['progress_percent']==37

def test_replay_does_not_invalidate_without_a_project_change(domain):
    key=uid();call(domain,'create',body=FIELDS,idempotency_key=key)
    before=lookup(domain)['catalog_version'];call(domain,'create',body=FIELDS,idempotency_key=key)
    assert lookup(domain,expected=before)['catalog_version']==before

def test_lookup_version_and_rows_share_one_sqlite_read_snapshot(domain,monkeypatch):
    p=create(domain);version=lookup(domain)['catalog_version'];original=domain.db.connect;changed=[];errors=[]
    @contextmanager
    def connection():
        with original() as con:
            def trace(sql):
                if sql.startswith('SELECT id,rating,version FROM projects') and not changed:
                    changed.append(True)
                    try:call(domain,'patch',target=p['project_id'],body={'rating':'S'},if_match='"rev-1"',idempotency_key=uid())
                    except Exception as error:errors.append(error)
            con.set_trace_callback(trace);yield con
    monkeypatch.setattr(domain.db,'connect',connection)
    result=lookup(domain,[p['project_id']],version)
    assert changed and not errors and result['catalog_version']==version
    assert result['items'][0]['rating']=='A' and result['items'][0]['revision']==1
    fresh=lookup(domain,[p['project_id']]);assert fresh['items'][0]['rating']=='S' and fresh['catalog_version']!=version

def test_missing_does_not_leak_another_scope(domain):
    p=create(domain)
    with domain.db.transaction() as con:con.execute('UPDATE projects SET tenant_id=? WHERE id=?',('foreign',p['project_id']))
    assert lookup(domain,[p['project_id']])['items']==[{'project_id':p['project_id'],'state':'missing','rating':None,'revision':None}]
    with pytest.raises(ValidationError):lookup(domain,principal={**USER,'tenant_id':'foreign'})

def test_read_has_no_persistent_effect_and_never_opens_another_store(domain,monkeypatch):
    p=create(domain);connect=sqlite3.connect;opened=[]
    def guarded(path,*args,**kwargs):
        opened.append(str(path));assert 'projects.db' in str(path);return connect(path,*args,**kwargs)
    def state():
        with domain.db.connect() as con:return hashlib.sha256('\n'.join(con.iterdump()).encode()).hexdigest()
    before=state();monkeypatch.setattr(sqlite3,'connect',guarded)
    lookup(domain);lookup(domain,[p['project_id'],ID]);assert state()==before and opened

def test_restart_restore_and_direction_rotation_invalidate_catalog(domain,tmp_path):
    p=create(domain);old=lookup(domain)['catalog_version']
    for service in (Service(domain.db),Service(domain.db,catalog_context='rotated synthetic transport identity')):
        with pytest.raises(DomainError) as exc:lookup(service,[p['project_id']],old)
        assert exc.value.code=='VERSION_CONFLICT'
    restored=tmp_path/'restored/projects/projects.db';restored.parent.mkdir(parents=True,mode=0o700)
    with domain.db.connect() as source,sqlite3.connect(restored) as target:source.backup(target)
    restored.chmod(0o600);service=Service(FormalDatabase(restored));assert lookup(service,[p['project_id']])['items'][0]['revision']==1
    with pytest.raises(DomainError):lookup(service,[p['project_id']],old)

def test_actual_private_handler_envelope_permissions_and_rotation(domain):
    p=create(domain);build='f'*40;token='r'*64
    cfg=IpcConfig(str(domain.db.path),token,build)
    def wire(**overrides):return {'operation':'ratings','contract':CONTRACT,'principal':USER,'request_id':uid(),
        'body':{'project_ids':[p['project_id'],ID],'expected_catalog_version':None},**overrides}
    headers={'authorization':'Bearer '+token,'x-ikun-build-sha':build}
    with TestClient(create_ipc_app(cfg),raise_server_exceptions=False) as client:
        first=client.post('/v1/rpc',headers=headers,json=wire());assert first.status_code==200
        value=first.json();old=value['data']['catalog_version'];assert value['request_id']==first.headers['x-request-id']
        assert client.post('/v1/rpc',headers={'cookie':'synthetic=not-service-auth'},json=wire()).status_code==401
        assert client.post('/v1/rpc',headers={**headers,'x-ikun-build-sha':'a'*40},json=wire()).status_code==403
        assert client.post('/v1/rpc',headers={**headers,'x-role':'superadmin'},json=wire(principal=None)).status_code==401
        assert client.post('/v1/rpc',headers=headers,json=wire(body={'project_ids':[],'expected_catalog_version':None,'rating':'S'})).status_code==422
        bad=client.post('/v1/rpc',headers=headers,json={'operation':'create','principal':USER,'request_id':uid(),'body':FIELDS,'idempotency_key':uid()})
        assert bad.status_code==403
    rotated=IpcConfig(str(domain.db.path),'t'*64,build)
    with TestClient(create_ipc_app(rotated),raise_server_exceptions=False) as client:
        assert client.post('/v1/rpc',headers=headers,json=wire()).status_code==401
        stale=client.post('/v1/rpc',headers={**headers,'authorization':'Bearer '+'t'*64},json=wire(body={'project_ids':[],'expected_catalog_version':old}))
        assert stale.status_code==409 and stale.json()['error']['code']=='VERSION_CONFLICT'

@pytest.mark.parametrize('suffix',['-wal','-shm'])
def test_path_checks_do_not_follow_or_restat_transient_sidecars(tmp_path,monkeypatch,suffix):
    path=tmp_path/'projects.db';path.touch();sidecar=Path(str(path)+suffix);sidecar.touch();original=Path.stat
    def checked(candidate,*,follow_symlinks=True):
        if candidate==sidecar and follow_symlinks:raise AssertionError('second following stat races SQLite removal')
        return original(candidate,follow_symlinks=follow_symlinks)
    monkeypatch.setattr(Path,'stat',checked);assert project_path(path)==path

def test_real_node_ratings_transport(tmp_path):
    root=Path(__file__).resolve().parents[4]
    # Lightweight source entry validation, not a claim that the old Next build was rebuilt.
    shutil.copyfile(root/'modules/projects/integration/website/lib/projects.ts',root/'modules/projects/.preview/apps/website/lib/projects.ts')
    node='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node'
    result=subprocess.run([node,'--import',str(root/'modules/projects/.preview/node_modules/tsx/dist/loader.mjs'),
        '--test',str(root/'modules/projects/integration/tests/ratings-ipc.test.mjs')],cwd=root,capture_output=True,text=True,timeout=15)
    (tmp_path/'ratings-node.tap').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
