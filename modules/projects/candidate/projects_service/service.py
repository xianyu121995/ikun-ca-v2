"""B2 transaction and transport adapter around the original CRUD and source resolver."""
import hashlib
import json
import re
import time
import uuid

from . import db as core
from .db import DomainError, now
from .migration import FormalDatabase
from .models import CoreProjectImport, CoreProjectPatch, normalize_website
from .queries import canonical, page, record, summary, milestones
from . import home
from .transport import CommandResult, Event, Fields, MembershipAction, Rpc, SCOPE, UUID4

WRITES={'create','patch','membership','delete','completion','completions','restore'}
READS={'get','list','command','changes','reconcile','summary','milestones'}

def route_identity(rpc):
    root='/api/v1/projects'
    if rpc.operation=='create':return 'POST',root
    if rpc.operation=='completions':return 'POST',root+'/completions'
    path=root+'/'+valid_id(rpc.target)
    return {'patch':('PATCH',path),'delete':('DELETE',path),'membership':('POST',path+'/home-membership'),
            'completion':('POST',path+'/completion'),'restore':('POST',path+'/restore')}[rpc.operation]

def receipt_route(method,path,contract):
    if method not in ('POST','PATCH','DELETE') or not isinstance(path,str) or not re.fullmatch(r'/api/v1/projects(?:/completions|/prj_'+UUID4+r'(?:/(?:home-membership|completion|restore))?)?',path):raise DomainError(422,'VALIDATION_ERROR','回执路径不受支持')
    root='/api/v1/projects';suffix=path.rsplit('/',1)[-1]
    if (path==root and method!='POST') or (suffix in ('completions','completion','restore','home-membership') and method!='POST') or (suffix.startswith('prj_') and method not in ('PATCH','DELETE')):raise DomainError(422,'VALIDATION_ERROR','回执方法不匹配')
    if contract not in ('phase2-v1.0.0','projects-home-v1'):raise DomainError(422,'VALIDATION_ERROR','回执协议不受支持')
    return method+' '+path+' '+contract


def valid_id(value,prefix='prj_'):
    if not isinstance(value,str) or not re.fullmatch(prefix+UUID4,value):
        raise DomainError(422,'VALIDATION_ERROR','ID 格式不正确')
    return value


def revision(value):
    if value is None:raise DomainError(428,'VALIDATION_ERROR','需要 If-Match')
    matched=re.fullmatch(r'"rev-([1-9][0-9]*)"',value)
    if not matched:raise DomainError(422,'VALIDATION_ERROR','If-Match 格式不正确')
    return int(matched[1])


def entity(con,project_id):
    return core.get_project(con,valid_id(project_id),SCOPE,include_removed=True,full=True)


def _legacy_error(error):
    codes={'not_found':'NOT_FOUND','project_deleted':'CONFLICT','duplicate_project':'CONFLICT',
           'mapping_conflict':'CONFLICT','version_conflict':'VERSION_CONFLICT','idempotency_conflict':'IDEMPOTENCY_CONFLICT'}
    if error.code in codes:
        return DomainError(409 if error.status==410 else error.status,codes[error.code],error.message)
    return error


class Service:
    def __init__(self,database:FormalDatabase):
        self.db=database

    def execute(self,rpc:Rpc):
        if rpc.operation in WRITES|READS:
            if rpc.principal is None:raise DomainError(401,'UNAUTHENTICATED','缺少网站验证的身份')
            if rpc.operation in WRITES and rpc.principal.role!='superadmin':
                raise DomainError(403,'FORBIDDEN','需要超级管理员权限')
        elif rpc.principal is not None:
            raise DomainError(403,'FORBIDDEN','服务操作不能冒用用户入口')
        try:
            if rpc.operation in WRITES:
                return self.write(rpc)
            if rpc.operation=='ingest':return self.ingest(rpc)
            if rpc.operation.startswith('outbox_'):return self.outbox(rpc)
            with self.db.connect() as con:
                con.execute('BEGIN')
                if rpc.operation=='list':return 200,page(con,rpc.query,rpc.contract),None
                if rpc.operation=='summary':return 200,summary(con,rpc.query),None
                if rpc.operation=='milestones':return 200,milestones(con,rpc.query),None
                if rpc.operation=='get':
                    row=entity(con,rpc.target);return 200,home.projection(con,row) if rpc.contract=='projects-home-v1' else record(row),f'"rev-{row["version"]}"'
                if rpc.operation=='receipt':
                    if rpc.source is None:raise DomainError(403,'FORBIDDEN','来源凭证未绑定')
                    row=con.execute('SELECT * FROM event_inbox WHERE source=? AND event_id=? AND tenant_id=?',(rpc.source,valid_id(rpc.target,'evt_'),SCOPE)).fetchone()
                    if not row:raise DomainError(404,'NOT_FOUND','受理回执不存在')
                    return 200,self.event_receipt(row,True),None
                if rpc.operation=='command':
                    row=con.execute('SELECT * FROM tracking_outbox WHERE command_id=? AND tenant_id=?',(valid_id(rpc.target,'cmd_'),SCOPE)).fetchone()
                    if not row:raise DomainError(404,'NOT_FOUND','命令不存在')
                    return 200,self.command(row,rpc.request_id),None
                if rpc.operation=='reconcile':
                    if set(rpc.query)!={'method','path','contract'}:raise DomainError(422,'VALIDATION_ERROR','需要完整操作路由')
                    key=valid_id(rpc.target,'')
                    route=receipt_route(**rpc.query)
                    row=con.execute('SELECT * FROM operation_receipts WHERE actor_id=? AND tenant_id=? AND route=? AND idempotency_key=?',
                                    (rpc.principal.user_id,SCOPE,route,key)).fetchone()
                    if not row:raise DomainError(404,'NOT_FOUND','操作回执不存在')
                    return 200,{'state':'succeeded','method':row['method'],'path':row['path'],'contract':row['contract'],'idempotency_key':key,
                                'http_status':row['status'],'result':json.loads(row['response_json']),'original_request_id':row['original_request_id'],'completed_at':row['created_at']},None
                if rpc.operation=='changes':
                    value=rpc.query.get('after',0)
                    if isinstance(value,bool) or not str(value).isdigit():raise DomainError(422,'VALIDATION_ERROR','事件游标格式不正确')
                    rows=con.execute('SELECT * FROM project_changes WHERE tenant_id=? AND sequence>? ORDER BY sequence LIMIT 100',(SCOPE,int(value))).fetchall()
                    return 200,{'items':[{'sequence':row['sequence'],'type':'project.updated','data':record(json.loads(row['record_json']))} for row in rows]},None
            raise DomainError(404,'NOT_FOUND','操作不存在')
        except DomainError as error:
            raise _legacy_error(error) from None

    def write(self,rpc):
        key=valid_id(rpc.idempotency_key,'')
        method,path=route_identity(rpc);route=receipt_route(method,path,rpc.contract)
        hashed=hashlib.sha256(canonical({'body':rpc.body,'if_match':rpc.if_match}).encode()).hexdigest()
        with self.db.transaction() as con:
            previous=con.execute('SELECT * FROM operation_receipts WHERE actor_id=? AND tenant_id=? AND route=? AND idempotency_key=?',(rpc.principal.user_id,SCOPE,route,key)).fetchone()
            if previous:
                if previous['body_hash']!=hashed:raise DomainError(409,'IDEMPOTENCY_CONFLICT','同一幂等键对应了不同操作')
                output=json.loads(previous['response_json'])
                revision_value=output.get('project',output).get('revision')
                return previous['status'],output,f'"rev-{revision_value}"' if revision_value else None
            if rpc.operation=='completions':
                if set(rpc.body)!={'items'} or not isinstance(rpc.body['items'],list) or not 1<=len(rpc.body['items'])<=100:raise DomainError(422,'VALIDATION_ERROR','批量项目须为1–100项')
                items=rpc.body['items'];seen=set();rows=[]
                for item in items:
                    if not isinstance(item,dict) or set(item)-{'project_id','revision'}:raise DomainError(422,'VALIDATION_ERROR','批量字段不正确')
                    if 'revision' not in item:raise DomainError(428,'VALIDATION_ERROR','缺少 revision')
                    if type(item['revision']) is not int or item['revision']<1:raise DomainError(422,'VALIDATION_ERROR','revision 不正确')
                    project_id=valid_id(item.get('project_id'))
                    if project_id in seen:raise DomainError(422,'VALIDATION_ERROR','批量项目不能重复')
                    seen.add(project_id);row=entity(con,project_id)
                    if row['version']!=item['revision']:raise DomainError(409,'VERSION_CONFLICT','项目已变更，请重新读取')
                    rows.append(row)
                for row in rows:home.apply(con,rpc.model_copy(update={'operation':'completion','body':{}}),row)
                output={'items':[home.projection(con,entity(con,row['id'])) for row in rows]};status=200
            elif rpc.operation=='create' and rpc.contract=='projects-home-v1':
                project_id=home.apply(con,rpc);status=201;output=home.projection(con,entity(con,project_id))
            elif rpc.operation=='create':
                fields=Fields.model_validate(rpc.body)
                result=core.insert_project(con,fields.core(),rpc.principal.user_id,SCOPE,
                    extras={**fields.extras(),'home_membership':'active','discovered_at':None})
                project_id=result['id'];status=201;output=record(entity(con,project_id))
            else:
                project_id=valid_id(rpc.target)
                current=entity(con,project_id);version=revision(rpc.if_match)
                if current['version']!=version:raise DomainError(409,'VERSION_CONFLICT','项目已变更，请重新读取')
                if rpc.operation in ('completion','restore') or (rpc.operation=='patch' and rpc.contract=='projects-home-v1'):
                    home.apply(con,rpc,current)
                elif rpc.operation=='patch':
                    if not rpc.body or set(rpc.body)-set(Fields.model_fields):raise DomainError(422,'VALIDATION_ERROR','更新字段不正确')
                    merged=Fields.model_validate({**{k:v for k,v in record(current).items() if k in Fields.model_fields},**rpc.body})
                    if home.projection(con,current)['completion'] and (merged.progress_stage!=current['progress'] or merged.progress_percent!=current['progress_percent']):raise DomainError(409,'CONFLICT','请先恢复再修改进度')
                    patch=CoreProjectPatch(expected_version=version,**merged.core().model_dump(mode='json'))
                    core.patch_project(con,project_id,patch,rpc.principal.user_id,SCOPE,include_removed=True,extras=merged.extras())
                else:
                    if rpc.operation=='delete':
                        if rpc.body:raise DomainError(422,'VALIDATION_ERROR','DELETE 不接受资料')
                        action='remove'
                    else:action=MembershipAction.model_validate(rpc.body).action
                    core.delete_project(con,project_id,version,rpc.principal.user_id,SCOPE,home_action='active' if action=='add' else 'removed')
                status=200
                output=home.projection(con,entity(con,project_id)) if rpc.contract=='projects-home-v1' or rpc.operation in ('completion','restore') else record(entity(con,project_id))
            con.execute('INSERT INTO operation_receipts(actor_id,tenant_id,route,idempotency_key,body_hash,response_json,status,created_at,expires_at,original_request_id,method,path,contract) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (rpc.principal.user_id,SCOPE,route,key,hashed,canonical(output),status,now(),int(time.time())+7*86400,rpc.request_id,method,path,rpc.contract))
            revision_value=output.get('project',output).get('revision')
            return status,output,f'"rev-{revision_value}"' if revision_value else None

    @staticmethod
    def event_receipt(row,duplicate):
        return {key:row[key] for key in ('event_id','project_id','receipt_id','accepted_at','command_id')}|{'duplicate':duplicate}

    def ingest(self,rpc):
        event=Event.model_validate(rpc.body)
        if event.source!='hunter' or rpc.source!=event.source:
            raise DomainError(403,'FORBIDDEN','事件来源与方向凭证不匹配')
        hashed=hashlib.sha256(canonical(event.model_dump(mode='json')).encode()).hexdigest()
        payload=event.payload
        with self.db.transaction() as con:
            old=con.execute('SELECT * FROM event_inbox WHERE tenant_id=? AND source=? AND event_id=?',(SCOPE,event.source,event.event_id)).fetchone()
            if old:
                if old['body_hash']!=hashed:raise DomainError(409,'CONFLICT','事件 ID 对应不同资料，需人工核对')
                return 200,self.event_receipt(old,True),None
            aliases=[payload.source_entity_key]+(['x-user:'+payload.x_user_id] if payload.x_user_id else [])
            mapped={row['project_id'] for key in aliases for row in con.execute('SELECT project_id FROM project_sources WHERE tenant_id=? AND source=? AND external_id=?',(SCOPE,event.source,key))}
            if event.project_id:mapped.add(event.project_id)
            website_key=normalize_website(payload.project.website_url or '')[1]
            website=con.execute('SELECT id FROM projects WHERE tenant_id=? AND website_key=?',(SCOPE,website_key)).fetchone() if website_key else None
            if website:mapped.add(website['id'])
            if len(mapped)>1:raise DomainError(409,'CONFLICT','来源引用冲突，不能合并项目')
            target=next(iter(mapped),None)
            fields=payload.project
            for key in aliases:
                imported=CoreProjectImport(source=event.source,external_id=key,explicit_add=True,project_id=target,project=fields.core())
                result,_=core.import_project(con,imported,payload.actor.user_id,SCOPE,include_removed=True,
                    extras={**fields.extras(),'home_membership':'hidden','discovered_at':None})
                target=result['id']
            command={'schema_version':1,'command_id':payload.command_id,'tenant_id':SCOPE,'actor':payload.actor.model_dump(),
                     'operation':'tracking.create','project_id':target,'subscription_id':None,'expected_revision':None,
                     'payload':{'name':fields.name,'x_user_id':payload.x_user_id,'x_handle':payload.x_handle,'notes':fields.notes,'confirmed':True},'issued_at':now()}
            # Different event IDs for the same confirmed command still resolve one canonical effect.
            command_body=canonical({key:value for key,value in command.items() if key!='issued_at'})
            command_hash=hashlib.sha256(command_body.encode()).hexdigest()
            old_command=con.execute('SELECT command_hash FROM tracking_outbox WHERE command_id=?',(payload.command_id,)).fetchone()
            if old_command and old_command['command_hash']!=command_hash:
                raise DomainError(409,'CONFLICT','命令 ID 对应不同内容')
            if not old_command:
                con.execute('INSERT INTO tracking_outbox(command_id,tenant_id,project_id,command_json,command_hash,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                            (payload.command_id,SCOPE,target,canonical(command),command_hash,'pending',now(),now()))
            receipt_id='rcp_'+str(uuid.uuid4())
            con.execute('INSERT INTO event_inbox(source,event_id,tenant_id,body_hash,project_id,command_id,receipt_id,accepted_at) VALUES(?,?,?,?,?,?,?,?)',
                        (event.source,event.event_id,SCOPE,hashed,target,payload.command_id,receipt_id,now()))
            row=con.execute('SELECT * FROM event_inbox WHERE tenant_id=? AND source=? AND event_id=?',(SCOPE,event.source,event.event_id)).fetchone()
            return 200,self.event_receipt(row,False),None

    @staticmethod
    def command(row,request_id):
        remote=json.loads(row['remote_json']) if row['remote_json'] else {}
        return {'command_id':row['command_id'],'state':'pending' if row['state']=='sending' else row['state'],
                'project_id':row['project_id'],'subscription_id':remote.get('subscription_id'),'revision':remote.get('revision'),
                'updated_at':row['updated_at'],'error_code':row['error_code'],'request_id':request_id}

    def outbox(self,rpc):
        if rpc.source!='tracking':raise DomainError(403,'FORBIDDEN','需要网站到 Tracking 的方向能力')
        with self.db.transaction() as con:
            stamp=int(time.time())
            if rpc.operation=='outbox_claim':
                con.execute("UPDATE tracking_outbox SET state='unknown',lease_token=NULL,lease_until=NULL,error_code='UPSTREAM_TIMEOUT',updated_at=? WHERE state='sending' AND lease_until<=?",(now(),stamp))
                wanted=rpc.target
                if wanted is not None:valid_id(wanted,'cmd_')
                row=con.execute("SELECT * FROM tracking_outbox WHERE state IN ('pending','unknown','accepted','running') AND (lease_until IS NULL OR lease_until<=?)"+(' AND command_id=?' if wanted else '')+' ORDER BY updated_at,command_id LIMIT 1',(stamp,wanted) if wanted else (stamp,)).fetchone()
                if not row:return 200,{'item':None},None
                token=str(uuid.uuid4());action='send' if row['state']=='pending' and not row['delivered'] else 'reconcile'
                con.execute("UPDATE tracking_outbox SET state=?,lease_until=?,lease_token=?,attempts=attempts+1 WHERE command_id=?",('unknown' if action=='reconcile' else 'sending',stamp+30,token,row['command_id']))
                return 200,{'item':{'command':json.loads(row['command_json']),'action':action,'lease_token':token}},None
            if set(rpc.body)-{'lease_token','outcome','result'}:raise DomainError(422,'VALIDATION_ERROR','回执字段不正确')
            row=con.execute('SELECT * FROM tracking_outbox WHERE command_id=?',(valid_id(rpc.target,'cmd_'),)).fetchone()
            if not row or row['lease_token']!=rpc.body.get('lease_token') or not row['lease_until'] or row['lease_until']<stamp:
                raise DomainError(409,'VERSION_CONFLICT','投递租约已失效，先核对远端')
            outcome=rpc.body.get('outcome')
            if outcome not in ('unknown','not_found','received'):raise DomainError(422,'VALIDATION_ERROR','未知投递结果')
            result=rpc.body.get('result')
            if outcome=='received':
                result=CommandResult.model_validate(result).model_dump(mode='json')
                required={'command_id','state','project_id','subscription_id','revision','updated_at','error_code','request_id'}
                if not isinstance(result,dict) or set(result)!=required or result['command_id']!=row['command_id'] or result['project_id']!=row['project_id'] or result['state'] not in ('accepted','pending','running','succeeded','failed','unknown'):
                    raise DomainError(422,'VALIDATION_ERROR','远端命令投影不匹配')
                if result['subscription_id'] is not None:valid_id(result['subscription_id'],'sub_')
                state=result['state'];error=result['error_code']
            else:state='pending' if outcome=='not_found' else 'unknown';error=None if outcome=='not_found' else 'UPSTREAM_TIMEOUT'
            con.execute('UPDATE tracking_outbox SET state=?,remote_json=?,error_code=?,delivered=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE command_id=?',
                        (state,canonical(result) if result is not None else None,error,1 if outcome=='received' else 0 if outcome=='not_found' else row['delivered'],now(),row['command_id']))
            return 200,self.command(con.execute('SELECT * FROM tracking_outbox WHERE command_id=?',(row['command_id'],)).fetchone(),rpc.request_id),None
