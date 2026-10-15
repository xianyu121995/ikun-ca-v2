import asyncio
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, Path as ApiPath, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .db import Database, DomainError, create_project, delete_project, digest, get_project, import_project, list_projects, now, patch_project
from .models import Progress, ProjectFields, ProjectImport, ProjectPatch, Rating, SessionLogin

LOG = logging.getLogger('projects')
REQUEST_ID = ContextVar('projects_request_id', default='')
STATIC = Path(__file__).with_name('static')
ProjectId = Annotated[str, ApiPath(pattern=r'^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')]
PERMISSIONS = {
    'user': {'read'},
    'superadmin': {'read', 'create', 'edit', 'delete'},
}


def permissions(actor):
    return {'import'} if actor['kind'] == 'service' else PERMISSIONS[actor['role']]


@dataclass(frozen=True)
class Settings:
    db_path: str = 'data/projects.db'
    origin: str = 'http://127.0.0.1:8120'
    secure_cookie: bool = False
    proxy_authority: str | None = None
    rate_limit: int = 180
    login_limit: int = 10
    session_seconds: int = 8 * 3600

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('PROJECTS_ORIGIN 必须是单一可信来源')
        if self.origin.endswith('/'):
            raise ValueError('PROJECTS_ORIGIN 不应带末尾斜杠')
        if self.secure_cookie and parsed.scheme != 'https':
            raise ValueError('Secure cookie 必须配合 HTTPS')
        if min(self.rate_limit,self.login_limit,self.session_seconds) <= 0:
            raise ValueError('限流与会话期限必须为正数')
        if self.proxy_authority:
            proxy = urlsplit('http://' + self.proxy_authority)
            if proxy.hostname not in ('127.0.0.1','localhost','::1') or not proxy.port or proxy.username or proxy.password or proxy.path or proxy.query or proxy.fragment:
                raise ValueError('代理内部 Host 只能是显式 loopback host:port')
        if parsed.hostname not in ('127.0.0.1', 'localhost', '::1', 'testserver') and (parsed.scheme != 'https' or not self.secure_cookie):
            raise ValueError('公网服务必须使用 HTTPS 与 Secure cookie')

    @classmethod
    def from_env(cls):
        return cls(db_path=os.environ.get('PROJECTS_DB', 'data/projects.db'),
                   origin=os.environ.get('PROJECTS_ORIGIN', 'http://127.0.0.1:8120'),
                   secure_cookie=os.environ.get('PROJECTS_SECURE_COOKIE', '0') == '1',
                   proxy_authority=os.environ.get('PROJECTS_PROXY_AUTHORITY'))


class SecurityMiddleware:
    """Bound request buffering, enforce Host, and add headers without third party middleware."""
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        incoming_id = headers.get(b'x-request-id', b'').decode('ascii', errors='ignore')
        request_id = incoming_id if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', incoming_id) else str(uuid.uuid4())
        token = REQUEST_ID.set(request_id)
        try:
            await self.handle(scope, receive, send, headers, request_id)
        finally:
            REQUEST_ID.reset(token)

    async def handle(self, scope, receive, send, headers, request_id):
        async def reject(status,code,message):
            return await JSONResponse({'error':{'code':code,'message':message,'retryable':False},'request_id':request_id},status,
                headers={'X-Request-ID':request_id,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})(scope,receive,send)
        allowed_hosts = {urlsplit(self.settings.origin).netloc.lower()}
        if self.settings.proxy_authority:
            allowed_hosts.add(self.settings.proxy_authority.lower())
        if headers.get(b'host', b'').decode('latin1').lower() not in allowed_hosts:
            return await reject(400,'invalid_host','请求主机不受信任')
        chunks, size = deque(), 0
        while True:
            try:
                event = await asyncio.wait_for(receive(), timeout=10)
            except asyncio.TimeoutError:
                return await reject(408,'request_timeout','请求读取超时')
            if event['type'] == 'http.disconnect':
                return
            size += len(event.get('body', b''))
            if size > 48 * 1024:
                return await reject(413,'body_too_large','资料大小超过限制')
            chunks.append(event)
            if not event.get('more_body'):
                break

        async def bounded_receive():
            return chunks.popleft() if chunks else await receive()

        async def secure_send(event):
            if event['type'] == 'http.response.start':
                event['headers'] = list(event['headers']) + [
                    (b'x-request-id', request_id.encode()),
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'DENY'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                ]
            await send(event)
        await self.app(scope, bounded_receive, secure_send)


class RateLimiter:
    def __init__(self):
        self.buckets, self.lock = OrderedDict(), threading.Lock()

    def check(self, key, limit):
        stamp = time.monotonic()
        with self.lock:
            bucket = self.buckets.pop(key, deque())
            while bucket and bucket[0] <= stamp - 60:
                bucket.popleft()
            allowed = len(bucket) < limit
            if allowed:
                bucket.append(stamp)
            self.buckets[key] = bucket
            while len(self.buckets) > 4096:
                self.buckets.popitem(last=False)
            if not allowed:
                raise DomainError(429, 'rate_limited', '请求过于频繁，请稍后重试')


def create_app(settings=None):
    settings = settings or Settings.from_env()
    db, limiter = Database(settings.db_path), RateLimiter()

    @asynccontextmanager
    async def lifespan(app):
        db.migrate()
        yield

    app = FastAPI(title='ikun.ca 主页项目 API', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.db, app.state.settings = db, settings
    app.add_middleware(SecurityMiddleware, settings=settings)

    def error(status, code, message, **extra):
        headers = {'Retry-After': '60'} if status == 429 else {'Retry-After': '1'} if status == 503 else None
        return JSONResponse({'error': {'code': code, 'message': message, 'retryable': status in (429,502,503,504), **extra}, 'request_id': REQUEST_ID.get()}, status_code=status, headers=headers)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        # Pydantic's original errors include raw input; never echo secrets or imported payloads.
        fields = [{'field': '.'.join(str(p) for p in item['loc']), 'type': item['type']} for item in exc.errors()]
        return error(422, 'validation_error', '资料格式不正确，请检查字段及日期状态', fields=fields)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        if isinstance(exc, sqlite3.OperationalError) and ('locked' in str(exc) or 'busy' in str(exc)):
            return error(503, 'database_busy', '项目库正忙，请稍后重试')
        LOG.error('projects database error type=%s', type(exc).__name__)
        return error(500, 'database_error', '项目保存失败，请稍后重试')

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(exc.status_code, 'http_error', '请求地址或方法不正确')

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        request_id = REQUEST_ID.get()
        LOG.error('projects unexpected error request_id=%s type=%s', request_id, type(exc).__name__)
        return error(500, 'internal_error', '操作失败，请稍后重试')

    def trusted_origin(request):
        if request.headers.get('origin') != settings.origin:
            raise DomainError(403, 'invalid_origin', '请求来源不受信任')

    def authenticate(request: Request):
        authorization = request.headers.get('authorization', '')
        with db.connect() as con:
            if authorization:
                scheme, _, token = authorization.partition(' ')
                if scheme.lower() != 'bearer' or len(token) > 256:
                    raise DomainError(401, 'unauthenticated', '请先登录')
                principal = con.execute('SELECT id,tenant_id,kind,role,source FROM principals WHERE token_hash=? AND disabled=0', (digest(token),)).fetchone()
            else:
                session = request.cookies.get('projects_session', '')
                row = con.execute('SELECT p.id,p.tenant_id,p.kind,p.role,p.source,s.csrf_hash FROM sessions s JOIN principals p ON p.id=s.principal_id WHERE s.token_hash=? AND s.expires_at>? AND p.disabled=0',
                                  (digest(session), int(time.time()))).fetchone() if session else None
                if row and request.method not in ('GET', 'HEAD', 'OPTIONS'):
                    trusted_origin(request)
                    csrf = request.headers.get('x-csrf-token', '')
                    if not csrf or not secrets.compare_digest(digest(csrf), row['csrf_hash']):
                        raise DomainError(403, 'invalid_csrf', '会话校验失败，请重新登录')
                principal = row
        if principal is None:
            raise DomainError(401, 'unauthenticated', '请先登录')
        limiter.check('actor:' + principal['id'], settings.rate_limit)
        return dict(principal)

    def require(permission):
        def dependency(actor=Depends(authenticate)):
            if permission not in permissions(actor):
                raise DomainError(403, 'forbidden', '当前角色没有此操作权限')
            return actor
        return dependency

    @app.get('/healthz')
    def health():
        with db.connect() as con:
            con.execute('SELECT 1').fetchone()
        return {'status': 'ok', 'service': 'homepage-projects'}

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/assets/{name}', include_in_schema=False)
    def assets(name: Literal['home.css', 'home.js']):
        return FileResponse(STATIC / name)

    @app.post('/api/home/session')
    def login(data: SessionLogin, request: Request, response: Response):
        trusted_origin(request)
        limiter.check('login:' + (request.client.host if request.client else 'unknown'), settings.login_limit)
        session, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with db.transaction() as con:
            actor = con.execute('SELECT id,kind,role FROM principals WHERE token_hash=? AND disabled=0', (digest(data.token),)).fetchone()
            if actor is None:
                raise DomainError(401, 'unauthenticated', '凭证无效或已停用')
            if actor['kind'] == 'service':
                raise DomainError(403, 'forbidden', '模块导入凭证不能登录主页')
            con.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
            con.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(session), actor['id'], digest(csrf), int(time.time()) + settings.session_seconds))
        response.set_cookie('projects_session', session, max_age=settings.session_seconds, httponly=True, secure=settings.secure_cookie, samesite='strict', path='/')
        return {'role': actor['role'], 'permissions': sorted(PERMISSIONS[actor['role']]), 'csrf_token': csrf}

    @app.get('/api/home/session')
    def session(actor=Depends(require('read'))):
        return {'role': actor['role'], 'permissions': sorted(PERMISSIONS[actor['role']])}

    @app.delete('/api/home/session', status_code=204)
    def logout(request: Request, response: Response, actor=Depends(require('read'))):
        with db.transaction() as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?', (digest(request.cookies.get('projects_session', '')),))
        response.delete_cookie('projects_session', path='/')

    @app.get('/api/home/tracking')
    @app.get('/api/home/projects')
    def projects(q: str = Query(default='', max_length=200), rating: Rating | None = None, progress: Progress | None = None,
                 sort: Literal['updated','discovered_desc','discovered_asc','rating','token_date','name'] = 'updated',
                 limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000),
                 actor=Depends(require('read'))):
        with db.connect() as con:
            return list_projects(con, q.strip(), rating, progress, sort, limit, offset, actor['tenant_id'])

    @app.get('/api/home/important-times')
    def important_times(limit: int = Query(default=4, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000), actor=Depends(require('read'))):
        with db.connect() as con:
            con.execute('BEGIN')
            today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
            where = 'deleted_at IS NULL AND token_date>=? AND tenant_id=?'
            total = con.execute(f'SELECT COUNT(*) FROM projects WHERE {where}', (today, actor['tenant_id'])).fetchone()[0]
            rows = con.execute(f'SELECT * FROM projects WHERE {where} ORDER BY token_date,id LIMIT ? OFFSET ?', (today, actor['tenant_id'], limit, offset)).fetchall()
            items = [{'id': row['id'] + ':token', 'project_id': row['id'], 'project_name': row['name'], 'kind': 'tge',
                      'scheduled_at': row['token_date'], 'date_status': row['token_date_status']} for row in rows]
            con.commit()
        return {'items': items, 'total': total, 'limit': limit, 'offset': offset, 'server_time': now()}

    @app.get('/api/home/projects/{project_id}')
    def detail(project_id: ProjectId, actor=Depends(require('read'))):
        with db.connect() as con:
            return get_project(con, str(project_id), actor['tenant_id'])

    @app.post('/api/home/projects')
    def create(data: ProjectFields, response: Response, idempotency_key: Annotated[str, Header(min_length=8, max_length=128)], actor=Depends(require('create'))):
        with db.transaction() as con:
            project, created = create_project(con, data, actor['id'], idempotency_key, actor['tenant_id'])
        response.status_code = 201 if created else 200
        return {'project': project, 'created': created}

    @app.patch('/api/home/projects/{project_id}')
    def patch(project_id: ProjectId, data: ProjectPatch, actor=Depends(require('edit'))):
        with db.transaction() as con:
            return patch_project(con, str(project_id), data, actor['id'], actor['tenant_id'])

    @app.delete('/api/home/projects/{project_id}', status_code=204)
    def delete(project_id: ProjectId, expected_version: int = Query(ge=1), actor=Depends(require('delete'))):
        with db.transaction() as con:
            delete_project(con, str(project_id), expected_version, actor['id'], actor['tenant_id'])

    @app.post('/api/home/imports')
    def receive_import(data: ProjectImport, response: Response, actor=Depends(require('import'))):
        if actor['source'] != data.source:
            raise DomainError(403, 'source_forbidden', '导入凭证与资料来源不匹配')
        with db.transaction() as con:
            project, created = import_project(con, data, actor['id'], actor['tenant_id'])
        response.status_code = 201 if created else 200
        return {'project': project, 'created': created}

    @app.get('/api/home/import-receipts')
    def import_receipt(source: str = Query(pattern=r'^[a-z][a-z0-9_-]{0,63}$'),
                       external_id: str = Query(min_length=1,max_length=200), actor=Depends(require('import'))):
        if source != actor['source']:
            raise DomainError(403, 'source_forbidden', '只能查询本来源的回执')
        with db.connect() as con:
            row = con.execute('SELECT s.source,s.external_id,s.project_id,s.added_at,p.deleted_at FROM project_sources s JOIN projects p ON p.id=s.project_id WHERE s.tenant_id=? AND s.source=? AND s.external_id=?',
                              (actor['tenant_id'],source,external_id)).fetchone()
            if row is None:
                raise DomainError(404, 'not_found', '导入回执不存在')
        return {'source':row['source'],'external_id':row['external_id'],'project_id':row['project_id'],
                'accepted_at':row['added_at'],'deleted':row['deleted_at'] is not None}

    return app
