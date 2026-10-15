from __future__ import annotations

import asyncio
import hmac
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .config import Settings
from .engine import Engine
from .store import Conflict, Missing, Store

PREFIX = '/api/hunterradar/v1'
STATIC = Path(__file__).with_name('static')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class HunterAdd(Input):
    username: str = Field(min_length=1, max_length=16)
    note: str = Field(default='', max_length=2000)


class HunterPatch(Input):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)
    enabled: StrictBool | None = None


class Version(Input):
    expected_version: int = Field(ge=1)


class Review(Version):
    name: str = Field(max_length=120)
    description: str = Field(default='', max_length=10000)
    website: str = Field(default='', max_length=2000)
    notes: str = Field(default='', max_length=20000)
    rating: str = Field(default='待定', pattern=r'^(S|A|B|C|待定)$')
    category: str = Field(default='其他', pattern=r'^(DeFi|基础设施|AI|DePIN|RWA|消费应用|游戏|身份|钱包|社交|预测市场|隐私|其他)$')
    stage: str = Field(default='未知',pattern=r'^(早期|测试网|主网|已发币|未知)$')
    ignored: StrictBool = False


class Confirm(Version):
    confirmed: StrictBool


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def create_app(settings: Settings | None = None, *, worker=False, store=None, engine=None):
    settings = settings or Settings.load()
    store = store or Store(settings.db)
    engine = engine or (Engine(settings, store) if worker else None)
    if settings.v2_mode:
        from .formal_api import create_formal_app
        return create_formal_app(settings,store,engine)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(engine.run()) if worker and engine else None
        if task:
            await asyncio.sleep(0.05)
            if task.done():
                task.result()  # Duplicate worker fails startup visibly.
        try:
            yield
        finally:
            if task:
                engine.stop.set()
                try:
                    await asyncio.wait_for(task, 10)
                except asyncio.TimeoutError:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(title='HunterRadar', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware('http')
    async def boundary(request, call_next):
        supplied_id=request.headers.get('x-request-id','')
        request.state.request_id=supplied_id if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',supplied_id) else str(uuid.uuid4())
        host = request.url.hostname
        local = request.client and request.client.host in ('127.0.0.1','::1','testclient') and host in ('127.0.0.1','localhost','::1','testserver')
        role = None
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
        if settings.admin_token and hmac.compare_digest(supplied, settings.admin_token):
            role = 'admin'
        elif settings.view_token and hmac.compare_digest(supplied, settings.view_token):
            role = 'viewer'
        elif not settings.admin_token and local and not settings.v2_mode:
            role = 'admin'
        static_path = request.url.path in ('/hunterradar', PREFIX+'/page', PREFIX+'/assets/app.js', PREFIX+'/assets/style.css')
        if settings.v2_mode and not settings.admin_token and request.url.path.startswith('/internal/'):
            return JSONResponse({'error':{'code':'AUTH_NOT_CONFIGURED','message':'Internal API credential not configured','retryable':False},'request_id':request.state.request_id},503,headers={'X-Request-ID':request.state.request_id})
        if not role and request.url.path.startswith('/internal/'):
            return JSONResponse({'error':{'code':'UNAUTHENTICATED','message':'Service credential required','retryable':False},'request_id':request.state.request_id},401,headers={'X-Request-ID':request.state.request_id})
        if not role and request.url.path not in ('/health','/health/live','/health/ready') and not (local and static_path):
            return JSONResponse({'error':'unauthorized'}, 401)
        if request.method not in ('GET', 'HEAD'):
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.url.netloc:
                return JSONResponse({'error':'cross_origin_mutation_rejected'}, 403)
        request.state.role = role
        request.state.actor = 'service-admin' if supplied and role == 'admin' else 'local-admin' if role == 'admin' else 'viewer'
        if supplied and role=='admin':
            actor=request.headers.get('x-hunterradar-actor','')
            if actor and len(actor)<=200 and all(ord(c)>=32 for c in actor):
                request.state.actor=actor
        response = await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
        return response

    def admin(request):
        if request.state.role != 'admin':
            raise HTTPException(403, 'hunter_admin_required')

    @app.exception_handler(Conflict)
    async def conflict(_, error):
        return JSONResponse({'error':str(error)}, 409)

    @app.exception_handler(Missing)
    async def missing(_, error):
        return JSONResponse({'error':str(error)}, 404)

    @app.exception_handler(ValueError)
    async def bad_input(_, error):
        return JSONResponse({'error':'invalid_input'}, 422)

    @app.exception_handler(RequestValidationError)
    async def validation(_, error):
        return JSONResponse({'error':'invalid_request','fields':['.'.join(str(x) for x in item['loc']) for item in error.errors()]}, 422)

    @app.get('/health/live')
    @app.get('/health/ready')
    def v2_health(request: Request):
        return {'data':{'service':'hunter','status':'ready' if request.url.path.endswith('ready') else 'alive',
                        'external_io_enabled':settings.external_io_enabled},'request_id':request.state.request_id}

    @app.get('/internal/v1/status')
    def v2_status(request: Request):
        admin(request)
        return {'data':store.status() | {'service':'hunter','external_io_enabled':settings.external_io_enabled},
                'request_id':request.state.request_id}

    @app.get('/health')
    def health():
        return {'service':'hunterradar','api':'ok','worker_alive':store.status()['worker_alive']}

    @app.get('/hunterradar')
    @app.get(PREFIX+'/page')
    def page():
        return FileResponse(STATIC/'index.html')

    @app.get(PREFIX+'/assets/{asset}')
    def asset(asset: str):
        if asset not in ('app.js','style.css'):
            raise HTTPException(404)
        return FileResponse(STATIC/asset)

    @app.get(PREFIX+'/session')
    def session(request: Request):
        return {'role':'superadmin' if request.state.role=='admin' else 'user','can_manage':request.state.role=='admin','provider_keys':{
                'wss':bool(settings.token_6551),'rest':bool(settings.token_twitterapi)},
                'external_io_enabled':settings.external_io_enabled, 'project_receiver_configured':bool(settings.project_url)}

    @app.get(PREFIX+'/status')
    def status():
        return store.status() | {'external_io_enabled':settings.external_io_enabled,'budget_limits':{'6551':settings.daily_6551,'twitterapi':settings.daily_twitterapi}}

    @app.get(PREFIX+'/hunters')
    def hunters(request: Request):
        admin(request)
        return {'items':store.hunters()}

    @app.post(PREFIX+'/hunters', status_code=201)
    def add(body: HunterAdd, request: Request):
        admin(request)
        return store.add(body.username, body.note, request.state.actor)

    @app.patch(PREFIX+'/hunters/{identifier}')
    def patch(identifier: str, body: HunterPatch, request: Request):
        admin(request)
        return store.patch(identifier, body.expected_version, note=body.note, enabled=body.enabled, actor=request.state.actor)

    @app.delete(PREFIX+'/hunters/{identifier}')
    def remove(identifier: str, request: Request, expected_version: int = Query(ge=1)):
        admin(request)
        return store.patch(identifier, expected_version, delete=True, actor=request.state.actor)

    @app.post(PREFIX+'/hunters/{identifier}/recheck')
    def recheck(identifier: str, body: Version, request: Request):
        admin(request)
        return store.patch(identifier, body.expected_version, recheck=True, actor=request.state.actor)

    @app.get(PREFIX+'/signals')
    @app.get(PREFIX+'/aggregate')
    def signals(limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0)):
        rows = store.aggregate(limit=limit+1, offset=offset)
        more = len(rows)>limit
        rows = rows[:limit]
        for row in rows:
            for field in ('first_seen','last_seen','activated_at'):
                row[field] = iso(row[field])
        return {'items':rows,'limit':limit,'offset':offset,'next_offset':offset+limit if more else None}

    @app.get(PREFIX+'/discoveries/{target}')
    def discovery(target: str):
        return store.discovery(target)

    @app.get(PREFIX+'/discoveries')
    def discoveries(limit: int = Query(100,ge=1,le=100), offset: int = Query(0,ge=0)):
        rows=store.discoveries(limit=limit+1,offset=offset)
        return {'items':rows[:limit],'next_offset':offset+limit if len(rows)>limit else None}

    @app.put(PREFIX+'/discoveries/{target}/review')
    def review(target: str, body: Review, request: Request):
        admin(request)
        if body.website and (urlsplit(body.website).scheme not in ('http','https') or not urlsplit(body.website).hostname):
            raise ValueError('invalid_website')
        data = body.model_dump(exclude={'expected_version'})
        return store.review(target, body.expected_version, data, request.state.actor)

    @app.post(PREFIX+'/discoveries/{target}/confirm', status_code=202)
    def confirm(target: str, body: Confirm, request: Request):
        admin(request)
        if not body.confirmed:
            raise HTTPException(422, 'explicit_manual_confirmation_required')
        key = request.headers.get('idempotency-key','')
        if not re.fullmatch(r'[\x21-\x7e]{1,128}', key):
            raise HTTPException(422, 'idempotency_key_required')
        if settings.delivery_protocol=='v2-event' and not re.fullmatch(r'ten_[0-9a-f-]{36}',settings.tenant_id):
            raise HTTPException(503,'hunter_tenant_scope_not_configured')
        return store.confirm(target, body.expected_version, key, request.state.actor,
                             tenant_id=settings.tenant_id,protocol=settings.delivery_protocol)

    @app.post(PREFIX+'/tasks/{identifier}/retry')
    def retry(identifier: str, request: Request):
        admin(request)
        store.retry_task(identifier, request.state.actor)
        return {'status':'pending'}

    @app.get(PREFIX+'/events')
    async def events(request: Request):
        async def stream():
            # Invalidations contain no hunter identity. DB reads survive API/worker restart.
            while not await request.is_disconnected():
                yield 'event: refresh\ndata: '+json.dumps({'at':time.time()})+'\n\n'
                await asyncio.sleep(10)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering':'no'})

    return app
