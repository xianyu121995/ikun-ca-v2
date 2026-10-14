"""Verify main-site sessions through its API; never open an auth database."""

import hmac
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request

from .config import Config


class SessionVerifier:
    def __init__(self, cfg: Config, transport=None):
        self.cfg, self.transport = cfg, transport

    async def verify(self, request: Request):
        token = request.cookies.get(self.cfg.auth_cookie_name)
        if not token:
            raise HTTPException(401, "site session required")
        try:
            async with httpx.AsyncClient(
                timeout=5,
                follow_redirects=False,
                transport=self.transport,
                cookies={self.cfg.auth_cookie_name: token},
            ) as client:
                response = await client.get(
                    self.cfg.auth_session_url,
                    headers={"Host": urlsplit(self.cfg.auth_origin).netloc},
                )
            if response.status_code in (401, 403):
                raise HTTPException(response.status_code, "site session rejected")
            if response.status_code != 200:
                raise HTTPException(503, "site authentication unavailable")
            data = response.json()
            user, csrf = data["user"], data["csrf_token"]
            if user.get("must_change_password") or user.get("role") not in ("superadmin", "user"):
                raise HTTPException(403, "site permissions rejected")
            if not isinstance(user.get("id"), str) or not user["id"] or not isinstance(csrf, str) or not csrf:
                raise ValueError("invalid identity response")
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise HTTPException(503, "site authentication unavailable") from None
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("origin") != self.cfg.auth_origin:
                raise HTTPException(403, "site origin rejected")
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                raise HTTPException(403, "site CSRF rejected")
        return user, csrf
