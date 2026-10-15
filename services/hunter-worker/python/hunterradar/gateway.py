"""Opt-in website BFF. The host supplies its EXISTING session/permission check.

No database access, collectors, migration or modification of the old API routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .api import PREFIX


@dataclass(frozen=True)
class GatewaySettings:
    upstream: str = 'http://127.0.0.1:8766'
    admin_token: str = field(default='', repr=False)
    view_token: str = field(default='', repr=False)

    def __post_init__(self):
        parsed = urlsplit(self.upstream)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
                or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username):
            raise ValueError('gateway_upstream_must_be_local_service')
        if min(len(self.admin_token),len(self.view_token)) < 32 or self.admin_token == self.view_token:
            raise ValueError('gateway_requires_distinct_service_tokens')


def install_hunterradar_gateway(app, settings: GatewaySettings, authorize, client=None):
    """authorize(request, capability) -> authenticated actor id or None (async).

    capability: hunter.read, hunter.read_raw, hunter.manage. Check the real
    session and current role on EVERY call. Never trust role or actor headers.
    """
    router = APIRouter(prefix=PREFIX)

    @router.api_route('/{path:path}', methods=['GET','POST','PUT','PATCH','DELETE'])
    async def proxy(path: str, request: Request):
        # Restrict surface, and never proxy an arbitrary URL or query-supplied destination.
        segments = path.split('/')
        if not segments or segments[0] not in ('page','assets','session','status','signals','aggregate','hunters','discoveries','tasks') or '..' in segments:
            raise HTTPException(404)
        write = request.method != 'GET'
        capability = 'hunter.manage' if write else 'hunter.read_raw' if segments[0]=='hunters' else 'hunter.read'
        actor = await authorize(request, capability)
        if not isinstance(actor, str) or not actor or len(actor)>200:
            raise HTTPException(403, 'hunter_permission_required')
        if write:
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.url.netloc:
                raise HTTPException(403, 'cross_origin_mutation_rejected')
        # Resolve raw capability independently; read-only users never receive the admin token.
        can_manage = bool(await authorize(request, 'hunter.manage'))
        if segments[0]=='hunters' and not can_manage:
            raise HTTPException(403, 'hunter_admin_required')
        body = await request.body()
        if len(body)>65536:
            raise HTTPException(413)
        headers = {'Authorization':'Bearer '+(settings.admin_token if can_manage else settings.view_token),
                   'X-HunterRadar-Actor':actor, 'Content-Type':request.headers.get('content-type','application/json')}
        if request.headers.get('idempotency-key'):
            headers['Idempotency-Key'] = request.headers['idempotency-key']
        owned = client is None
        upstream = client or httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
        try:
            response = await upstream.request(request.method, settings.upstream.rstrip('/')+PREFIX+'/'+path,
                                              params=request.query_params, content=body, headers=headers)
            allowed = ('content-type','cache-control','content-security-policy','x-content-type-options','referrer-policy')
            return Response(response.content, status_code=response.status_code,
                            headers={key:value for key,value in response.headers.items() if key in allowed})
        except httpx.HTTPError:
            return JSONResponse({'error':'hunter_service_unavailable'},503)
        finally:
            if owned:
                await upstream.aclose()

    app.include_router(router)
    return app
