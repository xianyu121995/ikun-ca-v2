"""Private loopback B4 transport, called only by the B1 website adapter."""
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import re
import sqlite3
import time
import uuid

from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,StreamingResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool

from .formal import FormalService,account_dto
from .protocol import Failure,Principal,iso
from .store import Conflict,Missing
from .retention import TTL_US,micros

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate_json_key')
        result[key]=value
    return result

def create_formal_app(settings,store,engine=None):
    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(engine.run()) if engine else None
        if task:
            await asyncio.sleep(.05)
            if task.done():task.result()
        try:yield
        finally:
            if task:
                engine.stop.set()
                try:await asyncio.wait_for(task,10)
                except asyncio.TimeoutError:task.cancel();await asyncio.gather(task,return_exceptions=True)
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=store;service=FormalService(store)
    def failure(request,status,code,message):
        return JSONResponse({'error':{'code':code,'message':message,'retryable':code!='AUTH_NOT_CONFIGURED' and status in (429,502,503,504)},'request_id':request.state.request_id},status_code=status,
            headers={'x-request-id':request.state.request_id,'cache-control':'no-store','x-content-type-options':'nosniff'})
    def output(request,data,status=200,etag=None):
        return JSONResponse({'data':data,'request_id':request.state.request_id},status_code=status,headers={'etag':etag} if etag else None)

    @app.middleware('http')
    async def boundary(request,call_next):
        supplied=request.headers.get('x-request-id','')
        request.state.request_id=supplied if re.fullmatch(r'[A-Za-z0-9_-]{1,64}',supplied) else str(uuid.uuid4())
        path=request.url.path
        if path not in ('/health/live','/health/ready'):
            if not settings.admin_token:return failure(request,503,'AUTH_NOT_CONFIGURED','Hunter 方向凭据尚未配置')
            given=request.headers.get('authorization','')
            if not hmac.compare_digest(given.encode(),('Bearer '+settings.admin_token).encode()):return failure(request,401,'UNAUTHENTICATED','Hunter 服务凭据无效')
            if path.startswith('/api/v1/hunter'):
                try:principal=Principal.model_validate_json(request.headers.get('x-ikun-principal',''))
                except (ValueError,ValidationError):return failure(request,403,'FORBIDDEN','缺少网站刚验证的身份')
                request.state.principal=principal
                if ('/accounts' in path or request.method not in ('GET','HEAD')) and principal.role!='superadmin':return failure(request,403,'FORBIDDEN','需要超级管理员权限')
            if request.method not in ('GET','HEAD'):
                if request.headers.get('content-type','').split(';')[0].lower()!='application/json':return failure(request,415,'VALIDATION_ERROR','请使用 application/json')
                buffer=bytearray()
                try:
                    async with asyncio.timeout(5):
                        async for chunk in request.stream():
                            buffer.extend(chunk)
                            if len(buffer)>65536:return failure(request,413,'VALIDATION_ERROR','请求过大')
                except TimeoutError:return failure(request,408,'VALIDATION_ERROR','请求超时')
                request._body=bytes(buffer)
        response=await call_next(request)
        response.headers['cache-control']='no-store';response.headers['x-request-id']=request.state.request_id;response.headers['x-content-type-options']='nosniff'
        return response
    @app.exception_handler(Failure)
    async def failed(request,error):return failure(request,error.status,error.code,error.message)
    @app.exception_handler(Conflict)
    async def conflict(request,error):return failure(request,409,'VERSION_CONFLICT' if 'version' in str(error) else 'CONFLICT','记录已变更或稳定身份冲突，请核对原记录')
    @app.exception_handler(Missing)
    async def missing(request,error):return failure(request,404,'NOT_FOUND','记录不存在')
    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValueError)
    async def invalid(request,error):return failure(request,422,'VALIDATION_ERROR','字段或值不符合冻结协议')
    @app.exception_handler(sqlite3.Error)
    async def unavailable(request,error):return failure(request,503,'DB_UNAVAILABLE','Hunter 存储暂不可用；写入结果须核对原命令')
    @app.exception_handler(HTTPException)
    async def unknown(request,error):return failure(request,error.status_code,'NOT_FOUND' if error.status_code==404 else 'NOT_IMPLEMENTED','路径或方法不受支持')
    @app.exception_handler(Exception)
    async def internal(request,error):return failure(request,500,'INTERNAL_ERROR','Hunter 操作结果待核对')
    @app.get('/health/live')
    def live(request:Request):return output(request,{'service':'hunter','status':'alive'})
    @app.get('/health/ready')
    def ready(request:Request):
        try:store.inspect()
        except (ValueError,OSError,sqlite3.Error):return failure(request,503,'DB_UNAVAILABLE','Hunter 迁移或存储校验未通过')
        return output(request,{'service':'hunter','status':'ready','external_io_enabled':settings.external_io_enabled,
                               'project_delivery_enabled':settings.project_delivery_enabled,'schema_version':4,
                               'source_status':'未连接真实来源' if not settings.external_io_enabled else 'unknown'})
    @app.get('/internal/v1/status')
    def status(request:Request):return output(request,store.status()|{'service':'hunter','external_io_enabled':settings.external_io_enabled})
    @app.get('/api/v1/hunter/signals')
    @app.get('/api/v1/hunter/accounts')
    def page(request:Request):
        query={}
        for key in request.query_params:
            if len(request.query_params.getlist(key))!=1:raise Failure(422,'VALIDATION_ERROR','不接受重复查询字段')
            query[key]=request.query_params[key]
        return output(request,service.page('accounts' if request.url.path.endswith('accounts') else 'signals',query))
    @app.get('/api/v1/hunter/discoveries/{identifier}')
    def discovery(identifier:str,request:Request):
        if request.query_params:raise Failure(422,'VALIDATION_ERROR','不支持查询字段')
        data=service.discovery(identifier)
        return output(request,data,etag=f'"rev-{data["revision"]}"')
    @app.api_route('/api/v1/hunter/{path:path}',methods=['POST','PATCH','DELETE','PUT'])
    async def write(path:str,request:Request):
        if request.query_params:raise Failure(422,'VALIDATION_ERROR','不支持查询字段')
        try:body=json.loads(await request.body() or b'{}',object_pairs_hook=unique_object,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('finite_json_required')))
        except ValueError:raise Failure(422,'VALIDATION_ERROR','请求 JSON 无效') from None
        if not isinstance(body,dict):raise Failure(422,'VALIDATION_ERROR','需要对象')
        status,data,etag=await run_in_threadpool(service.write,request.state.principal,request.method,request.url.path,body,request.headers.get('idempotency-key'),request.headers.get('if-match'),request.state.request_id)
        return output(request,data,status,etag)
    @app.get('/internal/v1/commands/{identifier}')
    def command(identifier:str,request:Request):return output(request,service.command(identifier,request.state.request_id))
    @app.get('/internal/v1/events')
    def events(request:Request):
        if set(request.query_params)-{'after','limit'}:raise Failure(422,'VALIDATION_ERROR','查询字段不受支持')
        after=request.query_params.get('after','0');limit=request.query_params.get('limit','50')
        if not re.fullmatch(r'[0-9]{1,15}',after) or not limit.isdigit() or not 1<=int(limit)<=100:raise Failure(422,'VALIDATION_ERROR','事件游标无效')
        clock=store.retention_clock()
        with store.connect() as db:
            rows=db.execute("SELECT c.* FROM public_changes c WHERE sequence>? AND (type<>'hunter.discovery.updated' OR EXISTS(SELECT 1 FROM discoveries d WHERE d.discovery_id=c.entity_id AND d.first_discovered_at_us>?)) ORDER BY sequence LIMIT ?",(int(after),micros(clock)-TTL_US,int(limit))).fetchall()
            return output(request,{'items':[{'sequence':row['sequence'],'type':row['type'],'data':json.loads(row['data'])} for row in rows]})
    @app.api_route('/internal/v1/{path:path}',methods=['GET','POST','PATCH','DELETE'])
    def unsupported(path:str,request:Request):return failure(request,501,'NOT_IMPLEMENTED','Hunter 不接收未冻结的命令或订阅操作')
    return app
