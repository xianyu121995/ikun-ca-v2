from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from projects_service.db import DomainError
from projects_service.transport import Milestone
from test_b2_domain import domain, call, create, uid, FIELDS

EMPTY=dict(date=None,hour=None,title='',status='unconfirmed')
def home_create(service,*,milestone=EMPTY,complete=False,**fields):
    return call(service,'create',contract='projects-home-v1',idempotency_key=uid(),body={'fields':{**FIELDS,**fields},'milestone':milestone,'complete':complete})[1]

@pytest.mark.parametrize('hour',['00','23',None])
def test_milestone_hour_token_independence(domain,hour):
    m=dict(date='2026-12-31',hour=hour,title='主网上线',status='estimated')
    p=home_create(domain,milestone=m,token_date='2027-01-01',token_date_status='confirmed')
    assert p['milestone']==m and p['project']['token_date']=='2027-01-01'
    assert 'milestone' not in call(domain,'get',target=p['project']['project_id'])[1]

@pytest.mark.parametrize('value',[{**EMPTY,'hour':'00'},{**EMPTY,'status':'confirmed'},{**EMPTY,'date':'2026-02-30'},
    dict(date='2026-01-01',hour='24',title='event',status='confirmed'),dict(date='2026-01-01',hour='0',title='event',status='confirmed'),
    dict(date='2026-01-01',hour=None,title='',status='estimated'),dict(date='2026-01-01',hour=None,title='event',status='unconfirmed')])
def test_invalid_milestone(value):
    with pytest.raises(ValidationError):Milestone.model_validate(value)

def test_atomic_event_edit_and_completion(domain):
    p=home_create(domain,progress_percent=37);target=p['project']['project_id']
    with pytest.raises(ValidationError):call(domain,'patch',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-1"',body={'fields':{'notes':'bad'},'milestone':{**EMPTY,'hour':'24'}})
    assert call(domain,'get',target=target)[1]['notes']=='研究备注'
    p=call(domain,'patch',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-1"',body={'fields':{'progress_stage':'completed','notes':'done'},'milestone':{**EMPTY,'title':'保留'},'complete':True})[1]
    assert p['project']['revision']==2 and p['project']['home_membership']=='removed'
    assert p['completion']['previous_stage']=='researching' and p['completion']['previous_percent']==37
    original=deepcopy(p['completion'])
    p=call(domain,'completion',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-2"')[1]
    assert p['completion']==original and p['project']['revision']==2
    with pytest.raises(DomainError):call(domain,'patch',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-2"',body={'fields':{'progress_stage':'watching'}})
    p=call(domain,'restore',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-2"')[1]
    assert p['completion'] is None and p['project']['progress_stage']=='researching' and p['project']['progress_percent']==37
    p=call(domain,'restore',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-3"')[1]
    assert p['project']['revision']==3
    call(domain,'completion',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-3"')
    call(domain,'restore',target=target,contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-4"')
    with domain.db.connect() as con:assert con.execute('SELECT COUNT(*) FROM project_completions WHERE restored_at IS NOT NULL').fetchone()[0]==2

def test_creation_default_and_legacy_missing_snapshot(domain):
    p=home_create(domain,complete=True,progress_stage='completed')
    assert p['project']['revision']==1 and p['completion']['restore_basis']=='creation_default'
    q=call(domain,'restore',target=p['project']['project_id'],contract='projects-home-v1',idempotency_key=uid(),if_match='"rev-1"')[1]
    assert q['project']['progress_stage']=='researching' and q['project']['progress_percent'] is None
    old=create(domain,progress_stage='completed')
    for operation in ['completion','restore']:
        with pytest.raises(DomainError) as exc:call(domain,operation,target=old['project_id'],idempotency_key=uid(),if_match='"rev-1"')
        assert exc.value.code=='CONFLICT'

def test_batch_rollback_duplicates_and_replay(domain):
    a=create(domain);b=create(domain,name='second');items=[{'project_id':p['project_id'],'revision':p['revision']} for p in (a,b)]
    with pytest.raises(DomainError):call(domain,'completions',idempotency_key=uid(),body={'items':[items[0],{**items[1],'revision':2}]})
    assert call(domain,'get',target=a['project_id'])[1]['revision']==1
    with pytest.raises(DomainError):call(domain,'completions',idempotency_key=uid(),body={'items':[items[0],items[0]]})
    key=uid();one=call(domain,'completions',idempotency_key=key,body={'items':items})[1]
    assert one==call(domain,'completions',idempotency_key=key,body={'items':items})[1]
    assert len(one['items'])==2

def test_over_100_server_total_order_and_independent_events(domain):
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    for i in range(113):
        home_create(domain,name=f'项目{i:03}',milestone={'date':today,'hour':['00','23',None][i%3],'title':'event','status':'confirmed'},rating=['S','A','B'][i%3])
    other=create(domain,rating='D')
    query={'collection':'tracked','sort':'name','direction':'asc','limit':9}
    page=call(domain,'list',contract='projects-home-v1',query=query)[1]
    assert page['total']==113 and len(page['items'])==9 and page['items'][0]['project']['name']=='项目000'
    seen=[]
    while True:
        seen.extend(p['project']['project_id'] for p in page['items'])
        if not page['next_cursor']:break
        page=call(domain,'list',contract='projects-home-v1',query={**query,'cursor':page['next_cursor']})[1]
    assert len(seen)==len(set(seen))==113 and other['project_id'] not in seen
    events=call(domain,'milestones',query={})[1]
    assert len(events['items'])==3 and events['items'][0]['milestone']['hour']=='00'
    counts=call(domain,'summary')[1];assert counts['tracked_total']==113 and counts['other_total']==1
    assert call(domain,'list',contract='projects-home-v1',query={**query,'q':'项目112'})[1]['total']==1
    assert events==call(domain,'milestones',query={})[1]
    assert call(domain,'summary',query={'discovered_on':today})[1]['tracked_total']==0

def test_collections_partition_explicit_membership_and_cursor(domain):
    active=create(domain);unrated=create(domain,rating=None);hidden=create(domain,progress_stage='completed');removed=create(domain)
    with domain.db.transaction() as con:
        con.execute("UPDATE projects SET home_membership='hidden' WHERE id=?",(hidden['project_id'],))
        con.execute("UPDATE projects SET home_membership='removed' WHERE id=?",(removed['project_id'],))
    completed=home_create(domain,complete=True,progress_stage='completed')['project']
    groups={}
    for collection in ('tracked','completed','other'):
        result=call(domain,'list',contract='projects-home-v1',query={'collection':collection,'limit':100})[1]
        groups[collection]={p['project']['project_id'] for p in result['items']}
        assert result['total']==len(groups[collection])
    assert groups['tracked']=={active['project_id']} and groups['completed']=={completed['project_id']}
    assert groups['other']=={unrated['project_id'],hidden['project_id'],removed['project_id']}
    assert sum(map(len,groups.values()))==5
    empty=call(domain,'list',contract='projects-home-v1',query={'collection':'completed','home_membership':'active'})[1]
    assert empty['total']==0 and empty['items']==[]
    p=call(domain,'list',contract='projects-home-v1',query={'collection':'other','limit':1})[1]
    for change in [{'collection':'tracked'},{'home_membership':'active'}]:
        with pytest.raises(DomainError):call(domain,'list',contract='projects-home-v1',query={'collection':'other','limit':1,'cursor':p['next_cursor'],**change})
    for operation in ('summary','milestones'):
        with pytest.raises(DomainError):call(domain,operation,query={'collection':'tracked'})

def test_event_sort_known_hours_unknown_last_both_directions(domain):
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    for hour in ['23',None,'00']:home_create(domain,milestone={'date':today,'hour':hour,'title':'event','status':'confirmed'})
    home_create(domain)
    for direction,expected in [('asc',['00','23',None,None]),('desc',['23','00',None,None])]:
        rows=call(domain,'list',contract='projects-home-v1',query={'sort':'event','direction':direction})[1]['items']
        assert [p['milestone']['hour'] for p in rows]==expected
        assert rows[-1]['milestone']['date'] is None

@pytest.mark.parametrize('cursor',['',' ','\t','not-a-signed-cursor'])
def test_milestone_rejects_explicit_invalid_cursor(domain,cursor):
    with pytest.raises(DomainError) as exc:call(domain,'milestones',query={'cursor':cursor})
    assert exc.value.status==422 and exc.value.code=='VALIDATION_ERROR'

def test_milestone_cursor_pagination_and_query_binding(domain):
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    expected=[]
    for i in range(5):
        p=home_create(domain,milestone={'date':(today+timedelta(days=i)).isoformat(),'hour':'00','title':'event','status':'confirmed'},rating='A')
        expected.append(p['project']['project_id'])
    query={'window_days':'7','rating':'A','limit':2}
    page=call(domain,'milestones',query=query)[1];cursor=page['next_cursor'];seen=[]
    assert cursor
    for changed in ({'window_days':'30'},{'rating':'S'},{'limit':3}):
        with pytest.raises(DomainError) as exc:call(domain,'milestones',query={**query,'cursor':cursor,**changed})
        assert exc.value.status==422 and exc.value.code=='VALIDATION_ERROR'
    while True:
        seen.extend(item['project']['project_id'] for item in page['items'])
        if not page['next_cursor']:break
        page=call(domain,'milestones',query={**query,'cursor':page['next_cursor']})[1]
    assert seen==expected and len(set(seen))==5

def test_completion_concurrency_and_batch_missing_revision(domain):
    import concurrent.futures
    p=create(domain);target=p['project_id']
    with pytest.raises(DomainError) as exc:call(domain,'completions',idempotency_key=uid(),body={'items':[{'project_id':target}]})
    assert exc.value.status==428
    def finish():
        try:return call(domain,'completion',target=target,idempotency_key=uid(),if_match='"rev-1"')[0]
        except DomainError as error:return error.status
    with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:finish(),range(2)))
    assert sorted(results)==[200,409]
    with domain.db.connect() as con:assert con.execute('SELECT COUNT(*) FROM project_completions').fetchone()[0]==1

def test_receipt_contract_route_actor_scope_and_restart(domain):
    from projects_service.service import Service
    key=uid();p=call(domain,'create',contract='projects-home-v1',idempotency_key=key,body={'fields':FIELDS,'milestone':EMPTY,'complete':False})[1]
    query={'method':'POST','path':'/api/v1/projects','contract':'projects-home-v1'}
    receipt=call(Service(domain.db),'reconcile',target=key,query=query)[1]
    assert receipt['result']==p and receipt['http_status']==201
    for q in [{**query,'contract':'phase2-v1.0.0'},{**query,'path':'/api/v1/projects/completions'}]:
        with pytest.raises(DomainError) as exc:call(domain,'reconcile',target=key,query=q)
        assert exc.value.status==404
    with pytest.raises(DomainError) as exc:call(domain,'reconcile',target=uid(),query=query)
    assert exc.value.status==404

@pytest.mark.parametrize('category',['NFT','发射台','新协议','撸毛','链游',None])
def test_home_category_filter(domain,category):
    wanted=home_create(domain,name='分类项目',category=category)['project']
    home_create(domain,name='其他项目',category='NFT' if category!='NFT' else '新协议')
    result=call(domain,'list',contract='projects-home-v1',query={'category':category or 'none','limit':100})[1]
    assert result['total']==1
    assert result['items'][0]['project']['project_id']==wanted['project_id']


def test_home_category_filter_rejects_unknown(domain):
    with pytest.raises(DomainError):
        call(domain,'list',contract='projects-home-v1',query={'category':'invalid'})


def test_milestone_three_day_window_and_cursor_binding(domain):
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    expected = []
    for offset in range(5):
        project = home_create(domain, milestone={'date': (today + timedelta(days=offset)).isoformat(), 'hour': '12', 'title': 'event', 'status': 'confirmed'}, rating='A')
        if offset <= 3:
            expected.append(project['project']['project_id'])
    query = {'window_days': '3', 'limit': 2}
    first = call(domain, 'milestones', query=query)[1]
    cursor = first['next_cursor']
    assert cursor
    with pytest.raises(DomainError):
        call(domain, 'milestones', query={**query, 'window_days': '7', 'cursor': cursor})
    second = call(domain, 'milestones', query={**query, 'cursor': cursor})[1]
    assert [p['project']['project_id'] for p in first['items'] + second['items']] == expected
    assert second['next_cursor'] is None
