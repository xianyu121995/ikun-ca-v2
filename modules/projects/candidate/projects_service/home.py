"""Approved projects-home-v1 transaction composition over the original CRUD."""
import uuid

from . import db as core
from .db import DomainError, now
from .models import CoreProjectPatch
from .queries import record
from .transport import Fields, Milestone, SCOPE

EMPTY={'date':None,'hour':None,'title':'','status':'unconfirmed'}

X_SOURCE='manual-tracking'  # same mapping key tracking_register uses, so both paths dedupe on one handle
X_PREFIX='x-handle:'

def official_x(con,project_id):
    row=con.execute("SELECT external_id FROM project_sources WHERE tenant_id=? AND project_id=? AND source=? AND external_id LIKE 'x-handle:%' ORDER BY added_at,external_id LIMIT 1",(SCOPE,project_id,X_SOURCE)).fetchone()
    return row[0][len(X_PREFIX):] if row else None

def save_official_x(con,project_id,handle,actor):
    current=official_x(con,project_id)
    if handle==current:return False
    if handle:
        owner=con.execute('SELECT project_id FROM project_sources WHERE tenant_id=? AND source=? AND external_id=?',(SCOPE,X_SOURCE,X_PREFIX+handle)).fetchone()
        if owner and owner[0]!=project_id:raise DomainError(409,'CONFLICT','该官推已关联其他项目')
    if current:con.execute('DELETE FROM project_sources WHERE tenant_id=? AND project_id=? AND source=? AND external_id=?',(SCOPE,project_id,X_SOURCE,X_PREFIX+current))
    if handle:con.execute('INSERT INTO project_sources(tenant_id,source,external_id,project_id,added_by,added_at) VALUES(?,?,?,?,?,?)',(SCOPE,X_SOURCE,X_PREFIX+handle,project_id,actor,now()))
    return True

def with_x(con,data):
    return {**data,'x_handle':official_x(con,data['project_id'])}

def projection(con,row):
    milestone=con.execute('SELECT date,hour,title,status FROM project_milestones WHERE project_id=?',(row['id'],)).fetchone()
    completion=con.execute('SELECT completion_id,previous_stage,previous_percent,completed_at,restore_basis FROM project_completions WHERE project_id=? AND restored_at IS NULL',(row['id'],)).fetchone()
    return {'project':with_x(con,record(row)),'milestone':dict(milestone) if milestone else dict(EMPTY),'completion':dict(completion) if completion else None}

def save_milestone(con,project_id,value):
    data=Milestone.model_validate(value).model_dump(mode='json')
    con.execute('INSERT INTO project_milestones(project_id,date,hour,title,status) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET date=excluded.date,hour=excluded.hour,title=excluded.title,status=excluded.status',
                (project_id,data['date'],data['hour'],data['title'],data['status']))

def snapshot(con,row,creation=False):
    current=con.execute('SELECT 1 FROM project_completions WHERE project_id=? AND restored_at IS NULL',(row['id'],)).fetchone()
    if current:return
    if not creation and row['progress']=='completed':raise DomainError(409,'CONFLICT','缺少可恢复的原始进度快照')
    con.execute('INSERT INTO project_completions VALUES(?,?,?,?,?,?,NULL)',('cmp_'+str(uuid.uuid4()),row['id'],
                'researching' if creation else row['progress'],None if creation else row['progress_percent'],now(),'creation_default' if creation else 'persisted'))

def apply(con,rpc,current=None):
    body=rpc.body
    if rpc.operation=='create':
        if set(body)!={'fields','milestone','complete'} or type(body['complete']) is not bool:raise DomainError(422,'VALIDATION_ERROR','复合创建字段不正确')
        fields=Fields.model_validate(body['fields']);milestone=Milestone.model_validate(body['milestone'])
        if body['complete']!=(fields.progress_stage=='completed'):raise DomainError(422,'VALIDATION_ERROR','完成状态不一致')
        p=core.insert_project(con,fields.core(),rpc.principal.user_id,SCOPE,extras={**fields.extras(),'home_membership':'removed' if body['complete'] else 'active','discovered_at':None})
        current=core.get_project(con,p['id'],SCOPE,include_removed=True,full=True)
        save_milestone(con,p['id'],milestone.model_dump(mode='json'))
        if fields.x_handle:
            save_official_x(con,p['id'],fields.x_handle,rpc.principal.user_id)
            core.audit(con,rpc.principal.user_id,'update',p['id'],('x_handle',),SCOPE)
        if body['complete']:snapshot(con,current,True)
        return p['id']
    view=projection(con,current);fields_data={k:v for k,v in view['project'].items() if k in Fields.model_fields};baseline=dict(fields_data)
    complete=rpc.operation=='completion';restore=rpc.operation=='restore';milestone=None
    if rpc.operation=='patch':
        if not body or set(body)-{'fields','milestone','complete'}:raise DomainError(422,'VALIDATION_ERROR','复合编辑字段不正确')
        changes=body.get('fields',{})
        if not isinstance(changes,dict) or set(changes)-set(Fields.model_fields):raise DomainError(422,'VALIDATION_ERROR','项目字段不正确')
        if 'complete' in body and body['complete'] is not True:raise DomainError(422,'VALIDATION_ERROR','恢复需使用显式入口')
        complete=body.get('complete',False)
        if view['completion'] and any(k in changes and changes[k]!=fields_data[k] for k in ('progress_stage','progress_percent')):raise DomainError(409,'CONFLICT','请先恢复再修改进度')
        fields_data.update(changes)
        if 'milestone' in body:milestone=Milestone.model_validate(body['milestone']).model_dump(mode='json')
        if complete and fields_data['progress_stage']!='completed':raise DomainError(422,'VALIDATION_ERROR','完成状态不一致')
        if not complete and not view['completion'] and fields_data['progress_stage']=='completed' and current['progress']!='completed':raise DomainError(422,'VALIDATION_ERROR','请显式完成项目')
    elif body:raise DomainError(422,'VALIDATION_ERROR','此操作仅接受空对象')
    membership=current['home_membership']
    if complete:
        snapshot(con,current)
        fields_data['progress_stage']='completed';membership='removed'
    if restore:
        completion=view['completion']
        if not completion:
            history=con.execute('SELECT 1 FROM project_completions WHERE project_id=? AND restored_at IS NOT NULL',(current['id'],)).fetchone()
            if not history or current['progress']=='completed':raise DomainError(409,'CONFLICT','缺少可恢复的原始进度快照')
            return current['id']
        fields_data['progress_stage']=completion['previous_stage'];fields_data['progress_percent']=completion['previous_percent'];membership='active'
        con.execute('UPDATE project_completions SET restored_at=? WHERE completion_id=?',(now(),completion['completion_id']))
    fields=Fields.model_validate(fields_data)
    changed=fields.model_dump(mode='json')!=Fields.model_validate(baseline).model_dump(mode='json') or membership!=current['home_membership'] or (milestone is not None and milestone!=view['milestone'])
    if rpc.operation=='patch' and not changed and not complete:raise DomainError(422,'VALIDATION_ERROR','没有实际修改或完成动作')
    if milestone is not None:save_milestone(con,current['id'],milestone)
    if changed and fields.x_handle!=baseline.get('x_handle'):save_official_x(con,current['id'],fields.x_handle,rpc.principal.user_id)
    if changed:
        patch=CoreProjectPatch(expected_version=current['version'],**fields.core().model_dump(mode='json'))
        core.patch_project(con,current['id'],patch,rpc.principal.user_id,SCOPE,include_removed=True,extras={**fields.extras(),'home_membership':membership})
    return current['id']
