from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def read_env(path: Path) -> dict[str, str]:
    """Parse data, never source a shell script or expand substitutions."""
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('\"\'')
    return result


@dataclass(frozen=True)
class Settings:
    db: Path = Path('var/hunter.db')
    host: str = '127.0.0.1'
    port: int = 8766
    admin_token: str = field(default='', repr=False)
    view_token: str = field(default='', repr=False)
    token_6551: str = field(default='', repr=False)
    token_twitterapi: str = field(default='', repr=False)
    daily_6551: int = 1000
    daily_twitterapi: int = 10000
    requests_per_minute: int = 30
    concurrency: int = 2
    rest_only: bool = False
    project_url: str = ''
    project_hosts: tuple[str, ...] = ('127.0.0.1', 'localhost')
    project_secret: str = field(default='', repr=False)
    timeout: float = 10
    external_io_enabled: bool = False
    v2_mode: bool = False
    tenant_id: str = 'ikun-main'
    delivery_protocol: str = 'project-task-v1'
    project_token: str = field(default='', repr=False)
    project_delivery_enabled:bool=False
    require_external_io_disabled:bool=False

    def __post_init__(self):
        if self.require_external_io_disabled and self.external_io_enabled:raise ValueError('external_collection_forbidden_in_this_release')
        if self.v2_mode:
            if self.tenant_id!='ikun-main' or self.host not in ('127.0.0.1','::1','localhost'):
                raise ValueError('invalid_v2_scope_or_bind')
            if self.admin_token and len(self.admin_token)<32:raise ValueError('v2_service_token_too_short')
            configured=[token for token in (self.admin_token,self.project_token,self.token_6551,self.token_twitterapi) if token]
            if len(configured)!=len(set(configured)):raise ValueError('direction_credentials_must_differ')
        if self.delivery_protocol not in ('project-task-v1','v2-event'):
            raise ValueError('unsupported_delivery_protocol')
        if self.host not in ('127.0.0.1', '::1', 'localhost') and not self.admin_token:
            raise ValueError('external_bind_requires_admin_token')
        if self.view_token and self.view_token == self.admin_token:
            raise ValueError('service_tokens_must_differ')
        if any(x < 1 for x in (self.daily_6551, self.daily_twitterapi, self.requests_per_minute, self.concurrency)):
            raise ValueError('invalid_budget_or_concurrency')
        if self.project_url:
            parsed = urlsplit(self.project_url)
            if (parsed.hostname not in self.project_hosts or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or not parsed.path.startswith('/')
                    or parsed.scheme not in ('http', 'https')
                    or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))
                    or (self.delivery_protocol=='v2-event' and parsed.path!='/internal/v1/ingest/hunter')
                    or (self.delivery_protocol=='project-task-v1' and len(self.project_secret)<32)
                    or (self.delivery_protocol=='v2-event' and len(self.project_token)<32)):
                raise ValueError('invalid_controlled_project_receiver')

    @classmethod
    def load(cls):
        # Formal jobs use explicit server environment/secret file, never cwd .env.
        env = read_env(Path('.env')) if os.environ.get('HUNTER_V2_MODE')!='1' and Path('.env').is_file() else {}
        env.update(os.environ)
        secret_keys = ('HUNTER_API_TOKEN','PROJECTS_INGEST_HUNTER_TOKEN','HUNTER_ADMIN_TOKEN','HUNTER_VIEW_TOKEN','OPENNEWS_TOKEN','TWITTERAPI_IO_API_KEY','HUNTER_PROJECT_TASK_SECRET')
        if env.get('HUNTER_SECRETS_FILE'):
            secret_env = read_env(Path(env['HUNTER_SECRETS_FILE']))
            for key in secret_keys:
                if not env.get(key):
                    env[key] = secret_env.get(key, '')
        return cls(db=Path(env.get('HUNTER_DB', 'var/hunter.db')),
                   host=env.get('HUNTER_HOST', '127.0.0.1'), port=int(env.get('HUNTER_PORT', '8766')),
                   admin_token=env.get('HUNTER_API_TOKEN') or env.get('HUNTER_ADMIN_TOKEN',''), view_token=env.get('HUNTER_VIEW_TOKEN', ''),
                   token_6551=env.get('OPENNEWS_TOKEN', ''), token_twitterapi=env.get('TWITTERAPI_IO_API_KEY', ''),
                   daily_6551=int(env.get('HUNTER_6551_DAILY_POINTS', '1000')),
                   daily_twitterapi=int(env.get('HUNTER_TWITTERAPI_DAILY_CREDITS', '10000')),
                   requests_per_minute=int(env.get('HUNTER_REQUESTS_PER_MINUTE', '30')),
                   concurrency=int(env.get('HUNTER_REST_CONCURRENCY', '2')),
                   rest_only=env.get('HUNTER_REST_ONLY')=='1',
                   project_url=env.get('HUNTER_PROJECT_TASK_URL', ''),
                   project_hosts=tuple(env.get('HUNTER_PROJECT_TASK_HOSTS', '127.0.0.1,localhost').split(',')),
                   project_secret=env.get('HUNTER_PROJECT_TASK_SECRET', ''),
                   external_io_enabled=env.get('HUNTER_EXTERNAL_IO_ENABLED')=='1',
                   v2_mode=env.get('HUNTER_V2_MODE')=='1',tenant_id=env.get('HUNTER_TENANT_ID','ikun-main'),
                   delivery_protocol=env.get('HUNTER_DELIVERY_PROTOCOL','project-task-v1'),
                   project_token=env.get('PROJECTS_INGEST_HUNTER_TOKEN',''),project_delivery_enabled=env.get('HUNTER_PROJECT_DELIVERY_ENABLED')=='1',
                   require_external_io_disabled=env.get('HUNTER_REQUIRE_EXTERNAL_IO_DISABLED','1' if env.get('HUNTER_V2_MODE')=='1' else '0')=='1')
