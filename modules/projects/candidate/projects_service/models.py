from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Rating = Literal['S', 'A', 'B', 'unrated']
Progress = Literal['todo', 'researching', 'watching', 'participating', 'completed', 'paused']
DateStatus = Literal['confirmed', 'estimated', 'unconfirmed']
Role = Literal['superadmin', 'user']
Name = Annotated[str, Field(min_length=1, max_length=120)]


def normalize_website(value: str) -> tuple[str, str | None]:
    if not value:
        return '', None
    if len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('官网格式不正确')
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('官网必须是无登录信息的 http/https 地址')
    host = parsed.hostname.encode('idna').decode('ascii').lower()
    port = parsed.port
    if ':' in host:
        host = f'[{host}]'
    if port and not ((parsed.scheme.lower() == 'https' and port == 443) or (parsed.scheme.lower() == 'http' and port == 80)):
        host += f':{port}'
    path = parsed.path.rstrip('/')
    # Query/fragment are attribution, never project identity. Different paths may be different projects.
    identity = host.removeprefix('www.') + path
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or '/', parsed.query, '')), identity


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProjectFields(StrictModel):
    name: Name
    rating: Rating = 'unrated'
    description: str = Field(default='', max_length=10000)
    website: str = Field(default='', max_length=2048)
    notes: str = Field(default='', max_length=10000)
    progress: Progress = 'todo'
    token_date: date | None = None
    token_date_status: DateStatus = 'unconfirmed'

    @field_validator('website')
    @classmethod
    def website_valid(cls, value):
        return normalize_website(value)[0]

    @model_validator(mode='after')
    def dates_match(self):
        if (self.token_date is None) != (self.token_date_status == 'unconfirmed'):
            raise ValueError('日期为空时状态必须是 unconfirmed；填写日期时须选择 confirmed 或 estimated')
        return self


class ProjectPatch(StrictModel):
    expected_version: int = Field(ge=1, strict=True)
    name: Name | None = None
    rating: Rating | None = None
    description: str | None = Field(default=None, max_length=10000)
    website: str | None = Field(default=None, max_length=2048)
    notes: str | None = Field(default=None, max_length=10000)
    progress: Progress | None = None
    token_date: date | None = None
    token_date_status: DateStatus | None = None

    @model_validator(mode='after')
    def reject_null_fields(self):
        for name in self.model_fields_set - {'token_date'}:
            if getattr(self, name) is None:
                raise ValueError(f'{name} 不能为 null')
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('没有需要更新的字段')
        return self


class ProjectImport(StrictModel):
    source: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    external_id: str = Field(min_length=1, max_length=200)
    explicit_add: Literal[True]
    project_id: str | None = Field(default=None, pattern=r'^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
    project: ProjectFields

    @field_validator('explicit_add', mode='before')
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError('仅接受用户明确加入的资料')
        return value


class SessionLogin(StrictModel):
    token: str = Field(min_length=32, max_length=256)
