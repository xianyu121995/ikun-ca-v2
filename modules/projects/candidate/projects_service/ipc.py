"""Private website-to-domain ASGI adapter. This module never authenticates humans."""
import asyncio
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .db import DomainError
from .migration import FormalDatabase
from .service import Service
from .transport import Rpc


@dataclass(frozen=True)
class IpcConfig:
    database: str
    token: str
    build_sha: str

    def __post_init__(self):
        if len(self.token)<32 or not re.fullmatch(r'[a-f0-9]{40}',self.build_sha):
            raise ValueError('INVALID_IPC_IDENTITY')

    @classmethod
    def environment(cls):
        return cls(os.environ['PROJECTS_DB'],os.environ['IKUN_IPC_TOKEN'],os.environ['IKUN_BUILD_SHA'])


def create_ipc_app(config:IpcConfig):
    database=FormalDatabase(config.database)
    service=Service(database,catalog_context=config.token)

    @asynccontextmanager
    async def lifespan(app):
        database.inspect()
        yield

    app=FastAPI(lifespan=lifespan,openapi_url=None,docs_url=None,redoc_url=None)
    app.state.service=service

    @app.middleware('http')
    async def boundary(request,call_next):
        candidate=request.headers.get('x-request-id','')
        request.state.request_id=candidate if re.fullmatch(r'[A-Za-z0-9_-]{1,64}',candidate) else str(uuid.uuid4())
        authorization=request.headers.get('authorization','')
        if not secrets.compare_digest(authorization.encode(),('Bearer '+config.token).encode()):
            return error(request,401,'UNAUTHENTICATED','IPC 方向凭据无效')
        if request.url.path!='/health/ready' and request.headers.get('x-ikun-build-sha')!=config.build_sha:
            return error(request,403,'FORBIDDEN','IPC 构建身份不匹配')
        if request.headers.get('content-length','').isdigit() and int(request.headers['content-length'])>131072:
            return error(request,413,'VALIDATION_ERROR','IPC 请求过大')
        response=await call_next(request)
        response.headers['cache-control']='no-store'
        response.headers['x-request-id']=request.state.request_id
        return response

    def error(request,status,code,message):
        return JSONResponse({'error':{'code':code,'message':message,'retryable':status in (429,502,503,504)},
                             'request_id':request.state.request_id},status_code=status,
                             headers={'cache-control':'no-store','x-request-id':request.state.request_id})

    @app.exception_handler(DomainError)
    async def domain_error(request,exc):return error(request,exc.status,exc.code,exc.message)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(request,exc):return error(request,422,'VALIDATION_ERROR','请求字段或值不符合 phase2 规范')

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(RuntimeError)
    async def storage(request,exc):return error(request,503,'DB_UNAVAILABLE','项目库暂不可用；写入结果须查询原回执')

    @app.exception_handler(Exception)
    async def failure(request,exc):return error(request,500,'INTERNAL_ERROR','项目操作未完成，请核对原回执')

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):return error(request,exc.status_code,'NOT_FOUND' if exc.status_code==404 else 'VALIDATION_ERROR','请求路径或方法不受支持')

    @app.get('/health/ready')
    def ready():
        try:database.inspect()
        except (OSError,sqlite3.Error,RuntimeError,ValueError):
            raise DomainError(503,'DB_UNAVAILABLE','项目库未初始化或版本校验失败')
        return {'data':{'service':'projects','ready':True,'writer':'projects-domain','build_sha':config.build_sha},'request_id':str(uuid.uuid4())}

    @app.post('/v1/rpc')
    async def rpc(request:Request):
        # Bound the actual stream, not only Content-Length, including slow/chunked bodies.
        buffer=bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    buffer.extend(chunk)
                    if len(buffer)>131072:raise DomainError(413,'VALIDATION_ERROR','IPC 请求过大')
        except TimeoutError:raise DomainError(408,'VALIDATION_ERROR','IPC 请求超时') from None
        try:data=Rpc.model_validate_json(buffer)
        except (ValidationError,ValueError):raise DomainError(422,'VALIDATION_ERROR','IPC 字段不正确') from None
        request.state.request_id=data.request_id
        # SQLite work is synchronous and isolated on FastAPI's bounded thread executor.
        from starlette.concurrency import run_in_threadpool
        status,output,etag=await run_in_threadpool(service.execute,data)
        return JSONResponse({'data':output,'request_id':data.request_id},status_code=status,
                            headers={'etag':etag} if etag else None)

    return app
