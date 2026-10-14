import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import Config
from .identity import SessionVerifier
from .store import Conflict, Missing, Store


@dataclass(frozen=True)
class Actor:
    subject: str
    role: Literal["superadmin", "reader"]
    csrf_token: str = ""


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Create(Body):
    project_id: str = Field(
        pattern=r"^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    name: str = Field(min_length=1, max_length=200)
    handle: str = Field(min_length=1, max_length=16)
    notes: str = Field(default="", max_length=4000)
    confirmed: Literal[True]


class Command(Body):
    expected_revision: int = Field(ge=1)


class Update(Command):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class Login(Body):
    token: str = Field(min_length=1, max_length=1024)


def create_app(
    cfg: Config,
    store: Store | None = None,
    authorize: Callable[[Request], Actor] | None = None,
    session_verifier: SessionVerifier | None = None,
) -> FastAPI:
    store = store or Store(cfg.db_path)
    app = FastAPI(title="ikun.ca Project Tracking", version="0.1.0")
    app.state.store = store
    verifier = session_verifier or SessionVerifier(cfg)
    static = Path(__file__).parent / "static"

    def credentials():
        admin, reader = cfg.secret("admin_token"), cfg.secret("read_token")
        if (admin and len(admin) < 32) or (reader and len(reader) < 32) or (admin and admin == reader):
            raise HTTPException(503, "invalid authentication configuration")
        return admin, reader

    def role_for(token):
        admin, reader = credentials()
        if token and admin and hmac.compare_digest(token, admin):
            return "superadmin"
        if token and reader and hmac.compare_digest(token, reader):
            return "reader"
        return None

    def same_origin(request: Request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "cross origin request rejected")

    async def actor(request: Request):
        if authorize:
            result = authorize(request)
            if not isinstance(result, Actor) or result.role not in ("reader", "superadmin"):
                raise HTTPException(403, "trusted authorization rejected")
            return result
        if cfg.auth_session_url:
            user, csrf = await verifier.verify(request)
            return Actor(user["id"], "superadmin" if user["role"] == "superadmin" else "reader", csrf)
        auth = request.headers.get("authorization", "")
        role = role_for(auth[7:]) if auth.startswith("Bearer ") else None
        if role is None and request.cookies.get("tracking_session"):
            role = store.session(request.cookies["tracking_session"])
            # Disabling configured credentials also revokes corresponding local sessions.
            admin, reader = credentials()
            if (role == "superadmin" and not admin) or (role == "reader" and not reader):
                role = None
            if request.method not in ("GET", "HEAD"):
                same_origin(request)
                if request.headers.get("x-tracking-csrf") != "1":
                    raise HTTPException(403, "CSRF header required")
        if role is None:
            raise HTTPException(401, "authentication required")
        return Actor(cfg.admin_subject if role == "superadmin" else "reader", role)

    def admin(user: Annotated[Actor, Depends(actor)]):
        if user.role != "superadmin":
            raise HTTPException(403, "superadmin required")
        return user

    def key(idempotency_key: Annotated[str, Header(min_length=8, max_length=128)]):
        return idempotency_key

    def engine():
        state = store.runtime()
        alive = bool(state["heartbeat"] and time.time() - state["heartbeat"] < 10)
        connected = bool(
            alive
            and state["connection"] == "connected"
            and state["pong_at"]
            and time.time() - state["pong_at"] < cfg.heartbeat_seconds + cfg.heartbeat_timeout + 5
        )
        return {
            "alive": alive,
            "connection": "connected"
            if connected
            else ("connecting" if alive and state["connection"] == "connecting" else "disconnected"),
            "last_heartbeat": state["heartbeat"],
            "last_pong": state["pong_at"],
            "error": state["error"],
        }

    def project(row):
        state = engine()
        fresh = bool(row["observed_at"] and time.time() - row["observed_at"] <= cfg.remote_fresh_seconds)
        remote = row["remote_state"] if fresh else "unknown"
        status = row["status"]
        if status == "running":
            status = (
                "monitoring" if remote == "active" and state["connection"] == "connected" else "recovering"
            )
        elif status in ("stopped", "removed") and remote != "absent":
            status = "unverified"
        result = {
            k: row[k]
            for k in (
                "project_id",
                "name",
                "handle",
                "notes",
                "desired",
                "revision",
                "generation",
                "error",
                "observed_at",
                "next_retry",
                "coverage",
                "confirmed_at",
                "created_at",
                "updated_at",
            )
        }
        return {
            **result,
            **store.tweet_stats(row["project_id"]),
            "remote_state": remote,
            "status": status,
            "engine": state,
        }

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(Missing)
    async def missing_handler(request, exc):
        return JSONResponse({"detail": "project not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        return JSONResponse({"detail": "invalid request or local configuration"}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        return JSONResponse({"detail": "invalid request fields"}, status_code=422)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/health/live")
    @app.get("/health/ready")
    def service_health():
        store.runtime()
        return {"data": {"service": "tracking", "status": "ready"}, "request_id": secrets.token_hex(16)}

    @app.get("/api/tracking/auth-mode")
    def auth_mode():
        return {"mode": "site" if cfg.auth_session_url else "standalone"}

    @app.post("/api/tracking/session")
    def login(body: Login, request: Request, response: Response):
        if cfg.auth_session_url or authorize:
            raise HTTPException(403, "use main-site login")
        same_origin(request)
        if not store.login_allowed(request.client.host if request.client else "local"):
            raise HTTPException(429, "try again in ten minutes")
        role = role_for(body.token)
        if role is None:
            raise HTTPException(401, "invalid access key")
        session = secrets.token_urlsafe(32)
        store.session(session, role)
        response.set_cookie(
            "tracking_session",
            session,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=3600,
            path="/api/tracking",
        )
        return {"role": role}

    @app.delete("/api/tracking/session")
    def logout(request: Request, response: Response, user=Depends(actor)):
        store.logout(request.cookies.get("tracking_session", ""))
        response.delete_cookie("tracking_session", path="/api/tracking")
        return {"ok": True}

    @app.get("/api/tracking/me")
    def me(user=Depends(actor)):
        return {"role": user.role, "subject": user.subject, "csrf_token": user.csrf_token}

    @app.get("/api/tracking/status")
    def status(user=Depends(actor)):
        rows = [project(r) for r in store.projects()]
        return {
            "engine": engine(),
            "projects": len(rows),
            "monitoring": sum(r["status"] == "monitoring" for r in rows),
            "pending_or_failed": sum(r["status"] not in ("monitoring", "stopped", "removed") for r in rows),
            "remote_enabled": cfg.remote_enabled and cfg.dedicated_account,
        }

    @app.get("/api/tracking/projects")
    def listing(include_removed: bool = False, user=Depends(actor)):
        return {"items": [project(r) for r in store.projects(include_removed)]}

    @app.post("/api/tracking/projects", status_code=202)
    def create(body: Create, user=Depends(admin), idem=Depends(key)):
        return project(store.mutate("create", body.project_id, body.model_dump(), user.subject, idem))

    @app.get("/api/tracking/projects/{project_id}")
    def detail(project_id: str, user=Depends(actor)):
        return project(store.get(project_id))

    @app.patch("/api/tracking/projects/{project_id}", status_code=202)
    def update(project_id: str, body: Update, user=Depends(admin), idem=Depends(key)):
        return project(
            store.mutate("update", project_id, body.model_dump(exclude_none=True), user.subject, idem)
        )

    @app.post("/api/tracking/projects/{project_id}/{action}", status_code=202)
    def command(
        project_id: str,
        action: Literal["start", "stop", "resume"],
        body: Command,
        user=Depends(admin),
        idem=Depends(key),
    ):
        return project(store.mutate(action, project_id, body.model_dump(), user.subject, idem))

    @app.delete("/api/tracking/projects/{project_id}", status_code=202)
    def remove(project_id: str, body: Command, user=Depends(admin), idem=Depends(key)):
        return project(store.mutate("remove", project_id, body.model_dump(), user.subject, idem))

    @app.get("/api/tracking/activities")
    def activities(
        project_id: str | None = None,
        after: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        user=Depends(actor),
    ):
        rows = store.activities(project_id, after, limit)
        return {"items": rows, "next_cursor": rows[-1]["seq"] if rows else after}

    @app.get("/api/tracking/latest")
    def latest(project_id: str | None = None, limit: int = Query(50, ge=1, le=200), user=Depends(actor)):
        return {"items": store.latest(project_id, limit)}

    @app.get("/api/tracking/projects/{project_id}/activities")
    def project_activities(
        project_id: str,
        after: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        user=Depends(actor),
    ):
        return activities(project_id, after, limit, user)

    @app.get("/tracking", include_in_schema=False)
    def page():
        return FileResponse(static / "index.html")

    from .v1 import install

    install(app, store, actor, admin, project, engine)
    app.mount("/tracking-assets", StaticFiles(directory=static), name="tracking-assets")
    return app
