"""Cursor projection around the existing project predicates and canonical rows."""
import base64
import hashlib
import hmac
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .db import DomainError, project_predicates
from .transport import SCOPE

PROJECT_TYPES=('NFT','发射台','新协议','撸毛','链游')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def record(row):
    return {'project_id':row['id'],'name':row['name'],'rating':None if row['rating']=='unrated' else row['rating'],
        'description':row['description'],'website_url':row['website'] or None,'notes':row['notes'],
        'category':row['category'],'progress_stage':row['progress'],'progress_percent':row['progress_percent'],
        'token_date':row['token_date'],'token_date_status':row['token_date_status'],'home_membership':row['home_membership'],
        'discovered_at':row['discovered_at'],'revision':row['version'],'created_at':row['created_at'],'updated_at':row['updated_at']}


def filters(query):
    allowed={'q','rating','progress_stage','home_membership','cursor','limit','sort','direction','discovered_on','collection','category'}
    if set(query)-allowed:
        raise DomainError(422,'VALIDATION_ERROR','查询字段不受支持')
    if not isinstance(query.get('q',''),str):
        raise DomainError(422,'VALIDATION_ERROR','搜索格式不正确')
    out={'q':query.get('q','').strip(),'rating':query.get('rating'),'progress_stage':query.get('progress_stage'),
         'home_membership':query.get('home_membership','active'),'sort':query.get('sort','discovered'),
         'direction':query.get('direction','desc'),'discovered_on':query.get('discovered_on'),'collection':query.get('collection'),'category':query.get('category')}
    # Owner decision 2026-10-19: project type filter (NFT/发射台/新协议/撸毛/链游, 'none' = 未分类).
    if out['category'] is not None and out['category'] not in PROJECT_TYPES+('none',):
        raise DomainError(422,'VALIDATION_ERROR','项目类型筛选不正确')
    out['membership_explicit']='home_membership' in query
    if not isinstance(out['q'],str) or len(out['q'])>200 or out['rating'] not in (None,'S','A','B','C','D','unrated') or out['progress_stage'] not in (None,'todo','researching','watching','participating','completed','paused'):
        raise DomainError(422,'VALIDATION_ERROR','搜索或筛选格式不正确')
    if out['home_membership'] not in ('hidden','active','removed') or out['sort'] not in ('updated','name','rating','discovered','progress','event') or out['direction'] not in ('asc','desc') or out['collection'] not in (None,'tracked','completed','other'):
        raise DomainError(422,'VALIDATION_ERROR','成员关系或排序格式不正确')
    size=query.get('limit',50)
    if isinstance(size,bool) or not str(size).isdigit() or not 1<=int(size)<=100:
        raise DomainError(422,'VALIDATION_ERROR','每页数量须为 1–100')
    out['limit']=int(size)
    if out['discovered_on'] is not None:
        try:
            day=date.fromisoformat(out['discovered_on'])
            if day.isoformat()!=out['discovered_on']:raise ValueError()
        except (TypeError,ValueError):
            raise DomainError(422,'VALIDATION_ERROR','发现日期格式不正确')
    return out


def _encode(value,secret):
    raw=canonical(value).encode()
    signature=hmac.new(secret.encode(),raw,hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature+raw).decode().rstrip('=')


def _decode(value,secret):
    try:
        if not isinstance(value,str) or len(value)>2048:raise ValueError()
        raw=base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
        if not hmac.compare_digest(raw[:32],hmac.new(secret.encode(),raw[32:],hashlib.sha256).digest()):raise ValueError()
        return json.loads(raw[32:])
    except (ValueError,TypeError,KeyError):
        raise DomainError(422,'VALIDATION_ERROR','游标无效或与当前查询不匹配')


def page(con,query,contract='phase2-v1.0.0'):
    options=filters(query)
    if options['collection'] and contract!='projects-home-v1':raise DomainError(422,'VALIDATION_ERROR','集合查询需要 home-v1')
    binding=hashlib.sha256(canonical({'scope':SCOPE,'contract':contract,**options}).encode()).hexdigest()
    secret=con.execute("SELECT value FROM project_settings WHERE key='cursor_secret'").fetchone()[0]
    clauses,args=project_predicates(con,options['q'],options['rating'],options['progress_stage'],SCOPE,
                                  include_removed=True,membership=None if options['collection'] and 'home_membership' not in query else options['home_membership'])
    tracked="(home_membership='active' AND rating IN ('S','A','B'))"
    completed="(home_membership='removed' AND progress='completed')"
    if options['collection']:
        clauses.append({'tracked':tracked,'completed':completed,'other':f'NOT ({tracked} OR {completed})'}[options['collection']])
    if options['category']=='none':
        clauses.append("(category IS NULL OR category='')")
    elif options['category']:
        clauses.append('category=?');args.append(options['category'])
    if options['discovered_on']:
        day=date.fromisoformat(options['discovered_on'])
        start=datetime.combine(day,time.min,ZoneInfo('Asia/Shanghai'))
        end=start+timedelta(days=1)
        clauses.append('julianday(discovered_at)>=julianday(?) AND julianday(discovered_at)<julianday(?)')
        args.extend([start.isoformat(),end.isoformat()])
    direction=options['direction'].upper()
    # SQLite BINARY Unicode ordering is deliberate and stable; no browser locale re-sort.
    event_date='(SELECT date FROM project_milestones WHERE project_id=projects.id)'
    event_hour='(SELECT hour FROM project_milestones WHERE project_id=projects.id)'
    expressions={'updated':['updated_at'],'name':['name COLLATE BINARY'],'discovered':['discovered_at'],
        'rating':["CASE rating WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 ELSE NULL END"],
        'progress':["CASE progress WHEN 'todo' THEN 0 WHEN 'researching' THEN 1 WHEN 'watching' THEN 2 WHEN 'participating' THEN 3 WHEN 'completed' THEN 4 WHEN 'paused' THEN 5 END",'progress_percent'],
        'event':[event_date,event_hour]}[options['sort']]
    keys=[]
    for expression in expressions:keys.extend([(f'({expression}) IS NULL','ASC'),(f"COALESCE(({expression}),'')",direction)])
    keys.append(('id','ASC'))
    total=con.execute(f"SELECT COUNT(*) FROM projects WHERE {' AND '.join(clauses)}",args).fetchone()[0]
    after=query.get('cursor')
    if after is not None:
        cursor=_decode(after,secret)
        if not isinstance(cursor,dict) or cursor.get('query')!=binding or cursor.get('v')!=1 or not isinstance(cursor.get('after'),list) or len(cursor['after'])!=len(keys):
            raise DomainError(422,'VALIDATION_ERROR','游标不能跨查询使用')
        comparisons=[]
        for i,(expression,order) in enumerate(keys):
            comparisons.append('('+' AND '.join([f'({keys[j][0]})=?' for j in range(i)]+[f'({expression})'+('>' if order=='ASC' else '<')+'?'])+')')
            args.extend(cursor['after'][:i+1])
        clauses.append('('+' OR '.join(comparisons)+')')
    selections=','.join(f'({expression}) AS _key{i}' for i,(expression,_) in enumerate(keys))
    ordering=','.join(f'({expression}) {order}' for expression,order in keys)
    rows=con.execute(f"SELECT *,{selections} FROM projects WHERE {' AND '.join(clauses)} ORDER BY {ordering} LIMIT ?",(*args,options['limit']+1)).fetchall()
    more=len(rows)>options['limit'];rows=rows[:options['limit']]
    cursor=_encode({'v':1,'query':binding,'after':[rows[-1][f'_key{i}'] for i in range(len(keys))]},secret) if more else None
    from .home import projection
    output={'items':[projection(con,row) if contract=='projects-home-v1' else record(row) for row in rows],'next_cursor':cursor}
    if contract=='projects-home-v1':output['total']=total
    return output


def summary(con,query):
    if set(query)-{'discovered_on'}:raise DomainError(422,'VALIDATION_ERROR','计数查询字段不正确')
    day=filters(query)['discovered_on'];clause='';args=[SCOPE]
    if day:
        start=datetime.combine(date.fromisoformat(day),time.min,ZoneInfo('Asia/Shanghai'))
        clause=' AND julianday(discovered_at)>=julianday(?) AND julianday(discovered_at)<julianday(?)';args.extend([start.isoformat(),(start+timedelta(days=1)).isoformat()])
    grades={grade:con.execute("SELECT COUNT(*) FROM projects WHERE tenant_id=? AND home_membership='active' AND rating=?"+clause,[SCOPE,grade,*args[1:]]).fetchone()[0] for grade in ('S','A','B')}
    completed=con.execute("SELECT COUNT(*) FROM projects WHERE tenant_id=? AND home_membership='removed' AND progress='completed'",(SCOPE,)).fetchone()[0]
    other=con.execute("SELECT COUNT(*) FROM projects WHERE tenant_id=? AND NOT ((home_membership='active' AND rating IN ('S','A','B')) OR (home_membership='removed' AND progress='completed'))",(SCOPE,)).fetchone()[0]
    return {'tracked_total':sum(grades.values()),'by_rating':grades,'completed_total':completed,'other_total':other}


def milestones(con,query):
    if set(query)-{'rating','window_days','cursor','limit'}:raise DomainError(422,'VALIDATION_ERROR','事件查询字段不正确')
    window=query.get('window_days','all')
    if str(window) not in ('all','3','7','30','90'):raise DomainError(422,'VALIDATION_ERROR','时间窗口不正确')
    day=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    # Reuse the authenticated cursor query and DB ordering; independent of table filters/page.
    base={'collection':'tracked','sort':'event','direction':'asc','limit':query.get('limit',3)}
    if 'rating' in query:base['rating']=query['rating']
    if 'cursor' in query:base['cursor']=query['cursor']
    # Temporary SQL view is unnecessary: apply event bounds as an internal trusted clause.
    return milestone_page(con,base,day,window)


def milestone_page(con,base,day,window):
    # Dedicated projection with a query-bound cursor including today's date and window.
    options=filters(base);binding=canonical({'scope':SCOPE,'kind':'milestones','day':day.isoformat(),'window':str(window),**options})
    secret=con.execute("SELECT value FROM project_settings WHERE key='cursor_secret'").fetchone()[0]
    args=[SCOPE,day.isoformat()];where="p.tenant_id=? AND p.home_membership='active' AND p.rating IN ('S','A','B') AND m.date>=?"
    if str(window)!='all':where+=' AND m.date<=?';args.append((day+timedelta(days=int(window))).isoformat())
    if options['rating'] is not None:where+=' AND p.rating=?';args.append(options['rating'])
    if 'cursor' in base:
        c=_decode(base['cursor'],secret)
        if not isinstance(c,dict) or c.get('query')!=binding or not isinstance(c.get('after'),list) or len(c['after'])!=3:raise DomainError(422,'VALIDATION_ERROR','事件游标不匹配')
        d,h,p=c['after'];where+=" AND (m.date>? OR (m.date=? AND (COALESCE(m.hour,'99')>? OR (COALESCE(m.hour,'99')=? AND p.id>?))))";args.extend([d,d,h,h,p])
    rows=con.execute(f"SELECT p.*,m.date AS event_date,COALESCE(m.hour,'99') AS event_hour FROM projects p JOIN project_milestones m ON m.project_id=p.id WHERE {where} ORDER BY m.date,COALESCE(m.hour,'99'),p.id LIMIT ?",[*args,options['limit']+1]).fetchall()
    more=len(rows)>options['limit'];rows=rows[:options['limit']]
    from .home import projection
    items=[{'project':record(row),'milestone':projection(con,row)['milestone']} for row in rows]
    cursor=_encode({'query':binding,'after':[rows[-1]['event_date'],rows[-1]['event_hour'],rows[-1]['id']]},secret) if more else None
    return {'items':items,'next_cursor':cursor,'as_of_date':day.isoformat()}
