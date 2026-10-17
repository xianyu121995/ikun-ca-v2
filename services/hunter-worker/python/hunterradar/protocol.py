"""Frozen phase2-v1.0.0 boundary. No login or platform side effects."""
from datetime import date,datetime,timezone
import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel,ConfigDict,Field,StrictBool,field_validator,model_validator

SCOPE='ikun-main'
UUID4=r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat() if value is not None else None

class Failure(Exception):
    def __init__(self,status,code,message):self.status,self.code,self.message=status,code,message

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Principal(Strict):
    user_id:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')
    tenant_id:Literal['ikun-main']
    role:Literal['superadmin','user']

class ProjectFields(Strict):
    name:str=Field(min_length=1,max_length=120)
    rating:Literal['S','A','B','C','D']|None
    description:str=Field(max_length=4000)
    website_url:str|None=Field(max_length=2048)
    notes:str=Field(max_length=4000)
    category:str|None=Field(max_length=80)
    progress_stage:Literal['todo','researching','watching','participating','completed','paused']
    progress_percent:float|None=Field(ge=0,le=100,strict=True,allow_inf_nan=False)
    token_date:date|None
    token_date_status:Literal['confirmed','estimated','unconfirmed']
    @field_validator('name')
    @classmethod
    def nonempty(cls,value):
        if not value.strip():raise ValueError('empty_project_name')
        return value
    @field_validator('website_url')
    @classmethod
    def safe_url(cls,value):
        if value is not None:
            u=urlsplit(value)
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or '\\' in value or any(c.isspace() or ord(c)<33 for c in value):raise ValueError('unsafe_website')
            u.port
        return value
    @field_validator('token_date',mode='before')
    @classmethod
    def exact_date(cls,value):
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)):raise ValueError('date_required')
        return value
    @model_validator(mode='after')
    def consistent(self):
        if (self.token_date is None)!=(self.token_date_status=='unconfirmed'):raise ValueError('date_status_mismatch')
        return self

class MonitoringRequest(Strict):
    confirmed:StrictBool
    project:ProjectFields
    @model_validator(mode='after')
    def manual(self):
        if self.confirmed is not True:raise ValueError('explicit_confirmation_required')
        return self

class ResearchPatch(Strict):
    # Missing and explicit null are different; non-null fields reject a supplied null.
    name:str=Field(default=None,min_length=1,max_length=120)
    rating:Literal['S','A','B','C','D']|None=None
    description:str=Field(default=None,max_length=4000)
    website_url:str|None=Field(default=None,max_length=2048)
    notes:str=Field(default=None,max_length=4000)
    category:str|None=Field(default=None,max_length=80)
    progress_stage:Literal['todo','researching','watching','participating','completed','paused']=None
    progress_percent:float|None=Field(default=None,ge=0,le=100,strict=True,allow_inf_nan=False)
    token_date:date|None=None
    token_date_status:Literal['confirmed','estimated','unconfirmed']=None
    # Owner decision 2026-10-17: '忽略' hides the discovery from the default list (not part of ProjectFields).
    ignored:StrictBool=None
    @field_validator('name')
    @classmethod
    def name_valid(cls,value):return ProjectFields.nonempty(value)
    @field_validator('website_url')
    @classmethod
    def url_valid(cls,value):return ProjectFields.safe_url(value)
    @field_validator('token_date',mode='before')
    @classmethod
    def date_valid(cls,value):return ProjectFields.exact_date(value)
    @field_validator('progress_percent')
    @classmethod
    def zero(cls,value):return 0.0 if value==0 else value
    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:raise ValueError('empty_patch')
        return self

class AccountCreate(Strict):
    x_handle:str=Field(pattern=r'^[A-Za-z0-9_]{1,15}$')
    label:str=Field(max_length=120)
    notes:str=Field(max_length=4000)
    enabled:StrictBool
class AccountPatch(Strict):
    label:str=Field(max_length=120,default='')
    notes:str=Field(max_length=4000,default='')
    enabled:StrictBool=True
    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:raise ValueError('empty_patch')
        return self

def revision(value):
    if value is None:raise Failure(428,'VALIDATION_ERROR','需要 If-Match')
    m=re.fullmatch(r'"rev-([1-9][0-9]{0,15})"',value)
    if not m:raise Failure(422,'VALIDATION_ERROR','If-Match 格式不正确')
    return int(m[1])
def request_key(value):
    if not isinstance(value,str) or not re.fullmatch(UUID4,value):raise Failure(422,'VALIDATION_ERROR','需要 UUIDv4 Idempotency-Key')
    return value

def legacy_project(row,profile):
    if row['project_json']:return ProjectFields.model_validate_json(row['project_json']).model_dump(mode='json')
    # Legacy stage is a lifecycle/network label, not phase2 progress. Unknown stays todo/null.
    return dict(name=row['name'] or profile.get('target_name') or row['target'],rating=row['rating'] if row['rating'] in ('S','A','B','C','D') else None,
        description=row['description'] or profile.get('description') or '',website_url=row['website'] or None,notes=row['notes'],
        category=row['category'] if row['category'] not in ('其他','') else None,progress_stage='todo',progress_percent=None,token_date=None,token_date_status='unconfirmed')
