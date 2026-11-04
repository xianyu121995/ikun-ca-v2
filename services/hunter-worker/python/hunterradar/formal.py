"""B4 adapter over the existing Store. No second collector, account auth or other DB."""
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime,timezone

from .protocol import AccountCreate,AccountPatch,Failure,MonitoringRequest,Principal,ProjectFields,ResearchPatch,SCOPE,UUID4,canonical,digest,iso,legacy_project,request_key,revision
from .retention import PROTOCOL,TTL_US,micros,active,watermark
from .store import Conflict,Missing,WINDOW

from .ai_prefill import suggestion as ai_suggestion

def discovery_dto(db,target,now):
    now=watermark(db,now)/1e6
    row=db.execute('SELECT * FROM discoveries WHERE target=?',(target,)).fetchone()
    if not active(db,row,now):raise Missing('discovery_not_found')
    profile=db.execute('SELECT target_name,description FROM follow_events WHERE target=? ORDER BY id DESC LIMIT 1',(target,)).fetchone()
    identity=db.execute('SELECT * FROM target_identities WHERE anchor=?',(target,)).fetchone()
    counts=db.execute('SELECT count(DISTINCT hunter_x_id),min(window_at),max(window_at) FROM follow_events WHERE target=? AND target_id IS NOT NULL AND window_at>=? AND window_at<=?',(target,now-WINDOW,now)).fetchone()
    task=db.execute('SELECT * FROM task_outbox WHERE target=?',(target,)).fetchone()
    profile=dict(profile) if profile else json.loads(row['profile_json'] or '{}')
    try:stored=json.loads(row['profile_json'] or '{}')
    except (TypeError,ValueError):stored={}
    followers=stored.get('followers_count') if isinstance(stored,dict) else None
    if type(followers) is not int or followers<0:followers=None
    suggestion=ai_suggestion(db,row['discovery_id'])
    column_reason=row['rating_reason'] if 'rating_reason' in row.keys() and isinstance(row['rating_reason'],str) and row['rating_reason'].strip() else None
    if suggestion is None and row['rating']=='忽略' and not row['ignored']:
        suggestion={'name':row['name'] or profile.get('target_name') or row['target'],'rating':'忽略','rating_reason':column_reason or ''}
    elif isinstance(suggestion,dict) and column_reason and not suggestion.get('rating_reason'):
        suggestion=dict(suggestion,rating_reason=column_reason)
    return dict(discovery_id=row['discovery_id'],project_id=task['project_id'] if task else None,
        project=legacy_project(row,profile),x_user_id=identity['x_user_id'] if identity else None,x_handle=identity['current_handle'] if identity else target,
        profile_bio=profile.get('description') or '',followers=followers,signal_count=counts[0],first_seen_at=iso(counts[1]),last_seen_at=iso(counts[2]),
        discovered_at=iso(row['first_discovered_at']),review_state='tracking' if task else 'ignored' if row['ignored'] else 'reviewed' if row['project_json'] or row['name'] else 'pending',
        monitoring_state=task['public_state'] if task else None,revision=row['version'],ai_suggestion=suggestion)

def account_dto(db,row,now):
    states={r['key']:json.loads(r['value']) for r in db.execute("SELECT key,value FROM state WHERE key IN ('worker_heartbeat','last_pong_at','wss_state')")}
    alive=now-states.get('worker_heartbeat',0)<15
    fresh=alive and bool(row['enabled']) and bool(row['baseline_ready']) and (now-(states.get('last_pong_at') or 0)<65 and row['watch_covered'] if row['mode']=='WSS' else row['last_poll_at'] is not None and now-row['last_poll_at']<7200 and not row['poll_error'])
    if row['mode']=='WSS' and states.get('wss_state')=='disabled_rest_only':fresh=False
    return dict(account_id=row['id'],x_handle=row['username'],label=row['label'],notes=row['note'],enabled=bool(row['enabled']),baseline_ready=bool(row['baseline_ready']),
        connection='connected' if fresh else 'unconfigured' if row['profile_status']!='ready' else 'connecting' if alive and states.get('wss_state')=='connecting' and row['mode']=='WSS' else 'disconnected',
        last_signal_at=iso(db.execute('SELECT max(received_at) FROM follow_events WHERE hunter_id=?',(row['id'],)).fetchone()[0]),revision=row['version'])

def command_dto(row,request_id):
    return dict(command_id=row['command_id'],state=row['public_state'],project_id=row['project_id'],subscription_id=None,
        revision=row['command_revision'],updated_at=iso(row['updated_at'] or row['confirmed_at']),error_code=('UPSTREAM_TIMEOUT' if row['status']=='unknown' else 'UPSTREAM_UNAVAILABLE' if row['status']=='failed' else None),request_id=request_id)

class FormalService:
    def __init__(self,store):self.store=store

    def discovery(self,identifier,now=None):
        stamp=self.store.retention_clock(now)
        with self.store.connect() as db:
            row=db.execute('SELECT target FROM discoveries WHERE discovery_id=?',(identifier,)).fetchone()
            if not row:raise Missing('discovery_not_found')
            return discovery_dto(db,row['target'],stamp)

    def command(self,identifier,request_id):
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM task_outbox WHERE command_id=?',(identifier,)).fetchone()
            if not row:raise Missing('command_not_found')
            return command_dto(row,request_id)

    def page(self,kind,query,now=None):
        if set(query)-({'cursor','limit','q','rating','review_state','since','until'} if kind=='signals' else {'cursor','limit'}):raise Failure(422,'VALIDATION_ERROR','查询字段不受支持')
        try:
            if not re.fullmatch(r'[1-9][0-9]{0,2}',str(query.get('limit','50'))):raise ValueError()
            limit=int(query.get('limit',50))
            if not 1<=limit<=100:raise ValueError()
            filters={key:value for key,value in query.items() if key not in ('cursor','limit')}
            if filters.get('rating','all') not in ('all','S','A','B','C','D','unrated'):raise ValueError()
            if filters.get('review_state','all') not in ('all','pending','reviewed','tracking','ignored'):raise ValueError()
            for key in ('since','until'):
                if key in filters:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)',filters[key]):raise ValueError()
                    datetime.fromisoformat(filters[key].replace('Z','+00:00'))
            if filters.get('since') and filters.get('until') and datetime.fromisoformat(filters['since'].replace('Z','+00:00'))>datetime.fromisoformat(filters['until'].replace('Z','+00:00')):raise ValueError()
            binding=digest([SCOPE,kind,filters,limit]);clock=self.store.retention_clock(now);stamp=clock;after=None
            with self.store.connect() as db:
                secret=json.loads(db.execute("SELECT value FROM state WHERE key='cursor_secret'").fetchone()[0]).encode()
                if 'cursor' in query:
                    if len(query['cursor'])>4096:raise ValueError()
                    encoded,signature=query['cursor'].split('.')
                    if not hmac.compare_digest(hmac.new(secret,encoded.encode(),hashlib.sha256).hexdigest(),signature):raise ValueError()
                    cursor=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
                    if set(cursor)!={'binding','at','after'} or cursor['binding']!=binding or not isinstance(cursor['after'],list) or len(cursor['after'])!=2:raise ValueError()
                    stamp=float(cursor['at']);after=cursor['after']
                if kind=='accounts':
                    sql='SELECT * FROM hunters WHERE deleted_at IS NULL';params=[]
                    if after:sql+=' AND (created_at>? OR (created_at=? AND id>?))';params=[after[0],after[0],after[1]]
                    found=db.execute(sql+' ORDER BY created_at,id LIMIT ?',(*params,limit+1)).fetchall()
                    items=[account_dto(db,row,clock) for row in found[:limit]]
                    last=[found[limit-1]['created_at'],found[limit-1]['id']] if len(found)>limit else None
                else:
                    sql='''WITH counts AS (SELECT target,count(DISTINCT hunter_x_id) n FROM follow_events WHERE target_id IS NOT NULL AND window_at>=? AND window_at<=? GROUP BY target HAVING count(DISTINCT hunter_x_id)>=2)
                      SELECT d.* FROM discoveries d JOIN counts c USING(target) LEFT JOIN task_outbox o USING(target) LEFT JOIN target_identities i ON i.anchor=d.target WHERE d.first_discovered_at_us>?''';params=[clock-WINDOW,clock,micros(clock)-TTL_US]
                    if after:sql+=' AND (d.first_discovered_at<? OR (d.first_discovered_at=? AND d.discovery_id<?))';params.extend([after[0],after[0],after[1]])
                    if filters.get('q'):
                        if len(filters['q'])>200:raise ValueError()
                        sql+=" AND instr(lower(d.name||' '||d.description||' '||d.notes||' '||COALESCE(d.project_json,'')||' '||COALESCE(i.current_handle,d.target)||' '||COALESCE((SELECT description FROM follow_events e WHERE e.target=d.target ORDER BY e.id DESC LIMIT 1),'')),lower(?))>0";params.append(filters['q'].strip())
                    if filters.get('rating','all')!='all':
                        sql+=" AND CASE WHEN d.project_json IS NOT NULL THEN COALESCE(json_extract(d.project_json,'$.rating'),'unrated') WHEN d.rating IN ('S','A','B','C','D') THEN d.rating ELSE 'unrated' END=?";params.append(filters['rating'])
                    if filters.get('review_state','all')!='ignored':sql+=' AND d.ignored=0'
                    if filters.get('review_state','all')!='all':
                        sql+=" AND CASE WHEN o.id IS NOT NULL THEN 'tracking' WHEN d.ignored=1 THEN 'ignored' WHEN d.project_json IS NOT NULL OR d.name<>'' THEN 'reviewed' ELSE 'pending' END=?";params.append(filters['review_state'])
                    for key,op in [('since','>='),('until','<=')]:
                        if key in filters:sql+=' AND d.first_discovered_at'+op+'?';params.append(datetime.fromisoformat(filters[key].replace('Z','+00:00')).timestamp())
                    found=db.execute(sql+' ORDER BY d.first_discovered_at DESC,d.discovery_id DESC LIMIT ?',(*params,limit+1)).fetchall()
                    items=[discovery_dto(db,row['target'],clock) for row in found[:limit]]
                    last=[found[limit-1]['first_discovered_at'],found[limit-1]['discovery_id']] if len(found)>limit else None
                next_cursor=None
                if last:
                    encoded=base64.urlsafe_b64encode(canonical({'binding':binding,'at':stamp,'after':last}).encode()).decode().rstrip('=')
                    next_cursor=encoded+'.'+hmac.new(secret,encoded.encode(),hashlib.sha256).hexdigest()
                return {'items':items,'next_cursor':next_cursor}
        except (ValueError,TypeError,KeyError,OverflowError):raise Failure(422,'VALIDATION_ERROR','分页或筛选参数无效') from None

    def write(self,principal:Principal,method,path,body,key,if_match,request_id,now=None):
        if principal.role!='superadmin':raise Failure(403,'FORBIDDEN','需要超级管理员权限')
        request_key(key);stamp=self.store.retention_clock(now)
        research=method=='PATCH' and re.fullmatch(r'/api/v1/hunter/discoveries/[^/]+',path)
        if research:
            if not re.fullmatch(r'/api/v1/hunter/discoveries/dsc_'+UUID4,path):raise Failure(422,'VALIDATION_ERROR','发现 ID 无效')
            body=ResearchPatch.model_validate(body).model_dump(mode='json',exclude_unset=True)
        hashed=digest({'protocol':PROTOCOL,'body':body,'if_match':if_match} if research else {'body':body,'if_match':if_match});route=method+' '+path
        with self.store.transaction() as db:
            old=db.execute('SELECT * FROM operation_receipts WHERE actor_id=? AND scope=? AND route=? AND request_key=?',(principal.user_id,SCOPE,route,key)).fetchone()
            if old:
                if old['body_hash']!=hashed:raise Failure(409,'IDEMPOTENCY_CONFLICT','同一幂等键对应不同操作')
                return old['status'],json.loads(old['response_json']),old['etag']
            suffix=path.removeprefix('/api/v1/hunter/')
            if research:
                version=revision(if_match);identifier=suffix.split('/')[1]
                row=db.execute('SELECT * FROM discoveries WHERE discovery_id=?',(identifier,)).fetchone()
                if not active(db,row,stamp):raise Missing('discovery_not_found')
                if row['version']!=version:raise Failure(409,'VERSION_CONFLICT','发现记录已变更')
                current=discovery_dto(db,row['target'],stamp)
                fields={k:v for k,v in body.items() if k!='ignored'}
                if 'ignored' in body:db.execute('UPDATE discoveries SET ignored=? WHERE discovery_id=?',(int(body['ignored']),identifier))
                elif 'rating' in body and row['ignored']:
                    # A person picked S/A/B/C/D/待定 instead of 忽略; the row stays and shows again.
                    db.execute('UPDATE discoveries SET ignored=0 WHERE discovery_id=?',(identifier,))
                project=ProjectFields.model_validate(current['project']|fields).model_dump(mode='json') if fields or row['project_json'] else None
                if project is not None:db.execute('UPDATE discoveries SET project_json=? WHERE discovery_id=?',(canonical(project),identifier))
                db.execute('UPDATE discoveries SET version=version+1,updated_at=? WHERE discovery_id=?',(stamp,identifier))
                self.store.audit(db,principal.user_id,'discovery.research.patch',identifier,stamp,canonical({'before_revision':version,'after_revision':version+1,'fields':sorted(body),'body_hash':hashed,'request_id':request_id}))
                self.store.change(db,row['target'],stamp)
                output={'discovery_id':identifier,'revision':version+1,'saved_at':iso(stamp)};status=200;etag=f'"rev-{version+1}"'
            elif suffix=='accounts' and method=='POST':
                data=AccountCreate.model_validate(body)
                row=self.store.add(data.x_handle,data.notes,principal.user_id,stamp,label=data.label,enabled=data.enabled)
                output=account_dto(db,row,stamp);status=201;etag=f'"rev-{output["revision"]}"'
            elif suffix.startswith('accounts/') and method in ('PATCH','DELETE') and suffix.count('/')==1:
                identifier=suffix.split('/')[1];version=revision(if_match)
                if method=='DELETE':
                    if body:raise Failure(422,'VALIDATION_ERROR','DELETE 不接受资料')
                    self.store.patch(identifier,version,delete=True,actor=principal.user_id,now=stamp)
                    output={'account_id':identifier,'removed':True};etag=f'"rev-{version+1}"'
                else:
                    data=AccountPatch.model_validate(body).model_dump(exclude_unset=True)
                    row=self.store.patch(identifier,version,note=data.get('notes'),label=data.get('label'),enabled=data.get('enabled'),actor=principal.user_id,now=stamp)
                    output=account_dto(db,row,stamp);etag=f'"rev-{row["version"]}"'
                status=200
            elif re.fullmatch(r'discoveries/[^/]+/monitoring-requests',suffix) and method=='POST':
                version=revision(if_match);data=MonitoringRequest.model_validate(body)
                identifier=suffix.split('/')[1]
                row=db.execute('SELECT * FROM discoveries WHERE discovery_id=?',(identifier,)).fetchone()
                if not active(db,row,stamp):raise Missing('discovery_not_found')
                if row['version']!=version:raise Failure(409,'VERSION_CONFLICT','发现记录已变更')
                current=discovery_dto(db,row['target'],stamp)
                if current['signal_count']<2 or row['ignored']:raise Failure(409,'CONFLICT','发现记录当前不符合人工加入条件')
                existing=db.execute('SELECT * FROM task_outbox WHERE target=?',(row['target'],)).fetchone()
                if existing:
                    try:
                        original=json.loads(existing['body'])['payload']['project']
                        intact=existing['body_hash']==hashlib.sha256(existing['body'].encode()).hexdigest()
                    except (ValueError,TypeError,KeyError):original=None;intact=False
                    if not existing['command_id'] or not intact or original!=data.project.model_dump(mode='json'):raise Failure(409,'CONFLICT','已有人工确认，资料与原快照不同，请核对原命令')
                    output=command_dto(existing,request_id)
                else:
                    command='cmd_'+str(uuid.uuid4());event_id='evt_'+str(uuid.uuid4())
                    identity=db.execute('SELECT entity_key FROM target_identities WHERE anchor=?',(row['target'],)).fetchone()
                    project=data.project.model_dump(mode='json')
                    event={'schema_version':1,'event_id':event_id,'source':'hunter','event_type':'hunter.monitoring_requested','occurred_at':iso(row['first_discovered_at'] or stamp),'received_at':iso(stamp),'tenant_id':SCOPE,'project_id':None,'correlation_id':'cor_'+str(uuid.uuid4()),
                        'payload':{'command_id':command,'discovery_id':identifier,'source_entity_key':identity['entity_key'],'confirmed':True,'actor':principal.model_dump(),'project':project,'x_user_id':current['x_user_id'],'x_handle':current['x_handle']}}
                    serialized=canonical(event)
                    db.execute('INSERT INTO task_outbox(id,target,idempotency_key,request_key,request_hash,body,confirmed_by,confirmed_at,event_id,command_id,request_id,updated_at,discovery_id,target_x_user_id,source_entity_key,body_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (command,row['target'],command.removeprefix('cmd_'),str(uuid.uuid4()),hashed,serialized,principal.user_id,stamp,event_id,command,request_id,stamp,identifier,current['x_user_id'],identity['entity_key'],hashlib.sha256(serialized.encode()).hexdigest()))
                    db.execute('UPDATE discoveries SET project_json=?,version=version+1,updated_at=? WHERE target=?',(canonical(project),stamp,row['target']))
                    self.store.audit(db,principal.user_id,'monitoring.confirm',identifier,stamp)
                    self.store.change(db,row['target'],stamp)
                    output=command_dto(db.execute('SELECT * FROM task_outbox WHERE command_id=?',(command,)).fetchone(),request_id)
                status=202;etag=f'"rev-{output["revision"]}"'
            else:raise Failure(501,'NOT_IMPLEMENTED','接口未实现')
            db.execute('INSERT INTO operation_receipts(actor_id,scope,route,request_key,body_hash,status,response_json,etag,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (principal.user_id,SCOPE,route,key,hashed,status,canonical(output),etag,stamp,stamp+7*86400))
            return status,output,etag
