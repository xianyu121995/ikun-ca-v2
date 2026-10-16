"""phase2-v1.0.0 transport validation; no sessions, passwords or credentials."""
from datetime import date, datetime, timezone
import re
from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .models import CoreProjectFields, StrictModel, normalize_website

SCOPE='ikun-main'
UUID4=r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
Rating=Literal['S','A','B','C','D']
Stage=Literal['todo','researching','watching','participating','completed','paused']
Membership=Literal['hidden','active','removed']


class Principal(StrictModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    user_id: str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')
    tenant_id: Literal['ikun-main']
    role: Literal['superadmin','user']


class Fields(StrictModel):
    name: str=Field(min_length=1,max_length=120)
    rating: Rating | None
    description: str=Field(max_length=4000)
    website_url: str | None=Field(max_length=2048)
    notes: str=Field(max_length=4000)
    category: str | None=Field(max_length=80)
    progress_stage: Stage
    progress_percent: float | None=Field(ge=0,le=100,allow_inf_nan=False,strict=True)
    token_date: date | None
    token_date_status: Literal['confirmed','estimated','unconfirmed']

    @field_validator('token_date',mode='before')
    @classmethod
    def exact_date(cls,value):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)):raise ValueError('ISO calendar date required')
        return value

    @field_validator('website_url')
    @classmethod
    def valid_url(cls,value):
        if value is not None and not value.strip():
            raise ValueError('website must be a URL or null')
        return normalize_website(value)[0] if value is not None else None

    @model_validator(mode='after')
    def date_status(self):
        if (self.token_date is None)!=(self.token_date_status=='unconfirmed'):
            raise ValueError('date/status mismatch')
        return self

    def core(self):
        return CoreProjectFields(name=self.name,rating=self.rating or 'unrated',description=self.description,
            website=self.website_url or '',notes=self.notes,progress=self.progress_stage,
            token_date=self.token_date,token_date_status=self.token_date_status)

    def extras(self):
        return {'category':self.category,'progress_percent':self.progress_percent}


class MembershipAction(StrictModel):
    action: Literal['add','remove']


class MonitoringPayload(StrictModel):
    command_id: str=Field(pattern='^cmd_'+UUID4+'$')
    discovery_id: str=Field(min_length=1,max_length=200)
    source_entity_key: str=Field(min_length=1,max_length=200)
    confirmed: StrictBool
    actor: Principal
    project: Fields
    x_user_id: str | None=Field(pattern=r'^[0-9]+$',max_length=40)
    x_handle: str=Field(pattern=r'^[A-Za-z0-9_]{1,15}$')

    @model_validator(mode='after')
    def manual(self):
        if self.confirmed is not True or self.actor.role!='superadmin':
            raise ValueError('explicit superadmin confirmation required')
        return self


class Event(StrictModel):
    schema_version: Literal[1]
    event_id: str=Field(pattern='^evt_'+UUID4+'$')
    source: Literal['hunter','tracking']
    event_type: Literal['hunter.monitoring_requested']
    occurred_at: datetime | None
    received_at: datetime
    tenant_id: Literal['ikun-main']
    project_id: str | None=Field(pattern='^prj_'+UUID4+'$')
    correlation_id: str=Field(min_length=1,max_length=200)
    payload: MonitoringPayload

    @field_validator('schema_version',mode='before')
    @classmethod
    def schema_number(cls,value):
        if type(value) is not int:
            raise ValueError('invalid version')
        return value

    @field_validator('occurred_at','received_at')
    @classmethod
    def timezone_required(cls,value):
        if value is not None and (value.tzinfo is None or value.utcoffset()!=timezone.utc.utcoffset(value)):
            raise ValueError('UTC timestamp required')
        return value

    @field_validator('occurred_at','received_at',mode='before')
    @classmethod
    def timestamp_string(cls,value):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)',value)):raise ValueError('UTC ISO timestamp string required')
        return value


class RatingsQuery(StrictModel):
    project_ids: list[str]=Field(max_length=200)
    expected_catalog_version: str | None=Field(min_length=1,max_length=128,strict=True)

    @field_validator('project_ids',mode='before')
    @classmethod
    def unique_ids(cls,value):
        if not isinstance(value,list) or any(not isinstance(item,str) or not re.fullmatch('prj_'+UUID4,item) for item in value):
            raise ValueError('canonical project IDs required')
        if len(value)!=len(set(value)):raise ValueError('duplicate project IDs')
        return value


class Rpc(StrictModel):
    operation: Literal['list','get','create','patch','membership','delete','ingest','receipt','command','reconcile',
                       'changes','outbox_claim','outbox_result','summary','milestones','completion','completions','restore','ratings']
    principal: Principal | None=None
    source: Literal['hunter','tracking'] | None=None
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    target: str | None=None
    query: dict=Field(default_factory=dict)
    body: dict=Field(default_factory=dict)
    idempotency_key: str | None=None
    if_match: str | None=None
    contract: Literal['phase2-v1.0.0','projects-home-v1','tracking-ratings-v1','tracking-observations-v1']='phase2-v1.0.0'

    @model_validator(mode='after')
    def ratings_contract(self):
        if (self.operation=='ratings')!=(self.contract=='tracking-ratings-v1'):
            raise ValueError('ratings operation requires its exact contract')
        if self.operation=='ratings':
            if self.model_fields_set & {'target','source','query','idempotency_key','if_match'}:
                raise ValueError('ratings is a dedicated read-only request')
            self.body=RatingsQuery.model_validate(self.body).model_dump()
        if self.contract=='tracking-observations-v1' and (self.operation not in ('ingest','receipt') or self.source!='tracking'):
            raise ValueError('observation contract only admits tracking ingest/receipt')
        return self


class Milestone(StrictModel):
    date: date | None
    hour: str | None=Field(pattern=r'^(?:[01][0-9]|2[0-3])$')
    title: str=Field(max_length=240)
    status: Literal['confirmed','estimated','unconfirmed']

    @field_validator('date',mode='before')
    @classmethod
    def exact_date(cls,value):return Fields.exact_date(value)

    @model_validator(mode='after')
    def consistent(self):
        if self.date is None:
            if self.hour is not None or self.status!='unconfirmed':raise ValueError('unknown date mismatch')
        elif not self.title.strip() or self.status=='unconfirmed':raise ValueError('dated event requires title/status')
        return self


class CommandResult(StrictModel):
    command_id: str=Field(pattern='^cmd_'+UUID4+'$')
    state: Literal['accepted','pending','running','succeeded','failed','unknown']
    project_id: str | None=Field(pattern='^prj_'+UUID4+'$')
    subscription_id: str | None=Field(pattern='^sub_'+UUID4+'$')
    revision: StrictInt | None=Field(ge=1)
    updated_at: datetime
    error_code: str | None=Field(max_length=64)
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')

    @field_validator('updated_at')
    @classmethod
    def utc(cls,value):
        return Event.timezone_required(value)

    @field_validator('updated_at',mode='before')
    @classmethod
    def timestamp_string(cls,value):return Event.timestamp_string(value)
