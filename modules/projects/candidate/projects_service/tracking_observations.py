"""Tracking observation inbox only: no tweet body storage or business-field writes."""
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .db import DomainError, now
from .transport import SCOPE, UUID4

CONTRACT='tracking-observations-v1'
CREATED='tracking.feed.activity.created.v1'
UPDATED='tracking.feed.activity.updated.v1'
NAMESPACE=uuid.UUID('c018deb2-7ccf-5092-8112-b5c9f71d40be')
TIMESTAMP=r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z'


class StrictObservation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

    @field_validator('*')
    @classmethod
    def unicode_scalar_values(cls,value):
        if isinstance(value,str):
            try:value.encode('utf-8',errors='strict')
            except UnicodeEncodeError:raise ValueError('invalid Unicode scalar') from None
        return value


def utc_string(value):
    if value is not None:
        if not isinstance(value,str) or not re.fullmatch(TIMESTAMP,value):raise ValueError('UTC required')
        datetime.fromisoformat(value.replace('Z','+00:00'))
    return value


class Activity(StrictObservation):
    activity_id: str=Field(min_length=40,max_length=40)
    subscription_id: str=Field(pattern='^sub_'+UUID4+'$')
    project_id: str=Field(pattern='^prj_'+UUID4+'$')
    project_name: str=Field(min_length=1,max_length=120)
    tweet_id: str=Field(pattern=r'^[0-9]{1,40}$')
    x_handle: str=Field(pattern=r'^[A-Za-z0-9_]{1,15}$')
    text: str=Field(max_length=20000)
    url: str=Field(max_length=128)
    occurred_at: str | None
    received_at: str
    source: Literal['wss','rest']
    generation: StrictInt=Field(ge=1,le=9223372036854775807)
    tweet_kind: Literal['original','quote','reply','repost','unknown']
    replay: StrictBool
    is_live_new: StrictBool

    @field_validator('occurred_at','received_at')
    @classmethod
    def times(cls,value):return utc_string(value)

    @model_validator(mode='after')
    def stable_identity(self):
        expected='act_'+str(uuid.uuid5(NAMESPACE,json.dumps([SCOPE,self.subscription_id,self.tweet_id],separators=(',',':'))))
        if self.activity_id!=expected or self.url!=f'https://x.com/{self.x_handle}/status/{self.tweet_id}':
            raise ValueError('activity identity or URL mismatch')
        return self


class Observation(StrictObservation):
    schema_version: Literal[1]
    event_id: str=Field(pattern='^evt_'+UUID4+'$')
    source: Literal['tracking']
    event_type: Literal[CREATED,UPDATED]
    occurred_at: str | None
    received_at: str
    tenant_id: Literal['ikun-main']
    project_id: str=Field(pattern='^prj_'+UUID4+'$')
    correlation_id: str=Field(min_length=40,max_length=40)
    payload: Activity

    @field_validator('schema_version',mode='before')
    @classmethod
    def integer_version(cls,value):
        if type(value) is not int:raise ValueError('integer schema version required')
        return value

    @field_validator('occurred_at','received_at')
    @classmethod
    def times(cls,value):return utc_string(value)

    @model_validator(mode='after')
    def matching_envelope(self):
        p=self.payload
        if (self.project_id,self.correlation_id,self.occurred_at,self.received_at)!=(p.project_id,p.activity_id,p.occurred_at,p.received_at):
            raise ValueError('envelope and activity mismatch')
        if self.event_type==CREATED:
            if p.tweet_kind not in ('original','quote') or p.source!='wss' or p.replay or not p.is_live_new:
                raise ValueError('created event is not a new allowed activity')
        elif not p.replay or p.is_live_new:raise ValueError('updated activity must be replay/correction')
        return self


def expected_hash(query):
    if set(query)-{'expected_hash'}:raise DomainError(422,'VALIDATION_ERROR','观察回执查询字段不正确')
    value=query.get('expected_hash')
    if 'expected_hash' in query and (not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value)):
        raise DomainError(422,'VALIDATION_ERROR','事件 hash 格式不正确')
    return value


def verify_hash(expected,actual):
    if expected is not None and not secrets.compare_digest(expected,actual):
        raise DomainError(409,'CONFLICT','事件 hash 不匹配，请核对原始事件')


def accept(con,body,query):
    if body.get('tenant_id',SCOPE)!=SCOPE:raise DomainError(403,'FORBIDDEN','事件范围无权限')
    event=Observation.model_validate(body)
    # Preserve the validated wire's original strings/integers, not normalized datetime output.
    hashed=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    verify_hash(expected_hash(query),hashed)
    old=con.execute('SELECT * FROM event_inbox WHERE tenant_id=? AND source=? AND event_id=?',(SCOPE,'tracking',event.event_id)).fetchone()
    if old:
        verify_hash(hashed,old['body_hash'])
        return old,True
    if not con.execute('SELECT 1 FROM projects WHERE id=? AND tenant_id=?',(event.project_id,SCOPE)).fetchone():
        raise DomainError(404,'NOT_FOUND','已关联项目不存在')
    alias='observations-v1:subscription:'+event.payload.subscription_id
    bound=con.execute('SELECT project_id FROM project_sources WHERE tenant_id=? AND source=? AND external_id=?',(SCOPE,'tracking',alias)).fetchone()
    if bound and bound['project_id']!=event.project_id:raise DomainError(409,'CONFLICT','订阅已关联其他项目')
    stamp=now()
    if not bound:
        con.execute('INSERT INTO project_sources(tenant_id,source,external_id,project_id,added_by,added_at) VALUES(?,?,?,?,?,?)',
                    (SCOPE,'tracking',alias,event.project_id,'tracking_observations_v1',stamp))
    con.execute('INSERT INTO event_inbox(source,event_id,tenant_id,body_hash,project_id,command_id,receipt_id,accepted_at) VALUES(?,?,?,?,?,NULL,?,?)',
                ('tracking',event.event_id,SCOPE,hashed,event.project_id,'rcp_'+str(uuid.uuid4()),stamp))
    return con.execute('SELECT * FROM event_inbox WHERE tenant_id=? AND source=? AND event_id=?',(SCOPE,'tracking',event.event_id)).fetchone(),False
