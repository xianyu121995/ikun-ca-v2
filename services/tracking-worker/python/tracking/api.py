"""Tracking service-only API. Website B1 guards own all human authentication."""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from . import commands, feed
from .config import Config
from .migration import inspect
from .protocol import UUID4, Command, DomainError, Principal, canonical
from .store import Store
from .views import page, subscription


def create_app(cfg: Config, store: Store | None = None):
    store = store or Store(cfg.db_path)
    app = FastAPI(title="Tracking service", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def reply(request, data, status=200, etag=None):
        return JSONResponse(
            {"data": data, "request_id": request.state.request_id},
            status_code=status,
            headers={"ETag": f'"rev-{etag}"'} if etag else {},
        )

    async def service(request: Request):
        try:
            token = cfg.secret("service_token")
            provider = cfg.secret("token")
        except (ValueError, OSError):
            raise DomainError(
                503, "AUTH_NOT_CONFIGURED", "tracking credential configuration invalid"
            ) from None
        if not token or len(token) < 32:
            raise DomainError(503, "AUTH_NOT_CONFIGURED", "tracking service credential not configured")
        if token == provider:
            raise DomainError(503, "AUTH_NOT_CONFIGURED", "direction credential must be independent")
        if not hmac.compare_digest(
            request.headers.get("authorization", "").encode(), ("Bearer " + token).encode()
        ):
            raise DomainError(401, "UNAUTHENTICATED", "direction credential required")
        for name in ("x-tenant", "x-tenant-id", "x-scope"):
            if request.headers.get(name) not in (None, "ikun-main"):
                raise DomainError(403, "FORBIDDEN", "scope rejected")
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise DomainError(422, "VALIDATION_ERROR", "duplicate query fields")
        if "tenant_id" in request.query_params:
            raise DomainError(403, "FORBIDDEN", "scope is server owned")

    @app.middleware("http")
    async def transport(request, next_call):
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else secrets.token_hex(16)
        )
        try:
            response = await next_call(request)
        except (sqlite3.Error, OSError, ValueError):
            response = JSONResponse(
                {
                    "error": {
                        "code": "DB_UNAVAILABLE",
                        "message": "tracking storage unavailable",
                        "retryable": True,
                    },
                    "request_id": request.state.request_id,
                },
                status_code=503,
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(DomainError)
    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(HTTPException)
    async def error(request, exc):
        status, code, message = (
            (exc.status, exc.code, exc.message)
            if isinstance(exc, DomainError)
            else (503, "DB_UNAVAILABLE", "tracking storage unavailable")
            if isinstance(exc, sqlite3.Error)
            else (exc.status_code, "NOT_FOUND", "route not found")
            if isinstance(exc, HTTPException)
            else (422, "VALIDATION_ERROR", "invalid request fields")
        )
        return JSONResponse(
            {
                "error": {"code": code, "message": message, "retryable": status in (429, 503)},
                "request_id": request.state.request_id,
            },
            status_code=status,
            headers={"Retry-After": "1"} if status == 429 else {},
        )

    async def body(request, *, maximum=65536):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise DomainError(415, "VALIDATION_ERROR", "JSON required")
        data = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > maximum:
                        raise DomainError(413, "VALIDATION_ERROR", "request too large")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TimeoutError):
            raise DomainError(422, "VALIDATION_ERROR", "invalid request JSON") from None

    def checked_id(value, prefix):
        if not re.fullmatch(prefix + UUID4, value):
            raise DomainError(422, "VALIDATION_ERROR", "invalid resource ID")
        return value

    def by_sub(sub, db):
        row = db.execute(
            "SELECT * FROM projects WHERE subscription_id=?", (checked_id(sub, "sub_"),)
        ).fetchone()
        if row is None:
            raise DomainError(404, "NOT_FOUND", "subscription not found")
        return dict(row)

    @app.get("/health/live")
    @app.get("/healthz")
    def live(request: Request):
        return reply(request, {"service": "tracking", "status": "alive"})

    @app.get("/health/ready")
    def ready(request: Request):
        inspect(cfg.db_path)
        return reply(
            request,
            {
                "service": "tracking",
                "status": "ready",
                "schema_version": 4,
                "external_collection_enabled": cfg.remote_enabled,
                "source_state": "unconfigured" if not cfg.remote_enabled else "not_verified",
            },
        )

    @app.post("/internal/v1/feed/{operation}", dependencies=[Depends(service)])
    async def published_feed(operation: str, request: Request):
        handlers = {
            "bases": (feed.BasisRequest, feed.basis),
            "snapshots": (feed.SnapshotRequest, feed.snapshot),
            "pages": (feed.PageRequest, feed.page),
        }
        if operation not in handlers:
            raise DomainError(404, "NOT_FOUND", "feed path not found")
        model, handler = handlers[operation]
        value = model.model_validate(await body(request, maximum=2 * 1024 * 1024))
        return reply(request, await asyncio.to_thread(handler, store, value))

    @app.post("/internal/v1/commands", dependencies=[Depends(service)])
    async def accept(request: Request):
        value = Command.model_validate(await body(request))
        return reply(request, commands.accept(store, value, request.state.request_id), 202)

    @app.get("/internal/v1/commands/{command_id}", dependencies=[Depends(service)])
    def command(command_id: str, request: Request):
        return reply(request, commands.query(store, checked_id(command_id, "cmd_"), request.state.request_id))

    @app.get("/internal/v1/subscriptions", dependencies=[Depends(service)])
    def subscriptions(request: Request):
        return reply(request, page(store, "subscriptions", dict(request.query_params),fresh_seconds=cfg.remote_fresh_seconds))

    @app.get("/internal/v1/subscriptions/{subscription_id}", dependencies=[Depends(service)])
    def detail(subscription_id: str, request: Request):
        with store.connect() as db:
            row = by_sub(subscription_id, db)
            return reply(
                request,
                subscription(store, row, db=db, fresh_seconds=cfg.remote_fresh_seconds),
                etag=row["revision"],
            )

    @app.patch("/internal/v1/subscriptions/{subscription_id}", dependencies=[Depends(service)])
    async def patch(subscription_id: str, request: Request, idempotency_key: str = Header()):
        checked_id(idempotency_key, "")
        value = await body(request)
        if set(value) != {"actor", "expected_revision", "patch"}:
            raise DomainError(422, "VALIDATION_ERROR", "patch envelope required")
        actor = Principal.model_validate(value["actor"])
        if actor.role != "superadmin":
            raise DomainError(403, "FORBIDDEN", "superadmin required")
        patch = value["patch"]
        rev = value["expected_revision"]
        if (
            not isinstance(patch, dict)
            or not patch
            or patch.keys() - {"name", "notes"}
            or type(rev) is not int
        ):
            raise DomainError(422, "VALIDATION_ERROR", "invalid patch")
        for key, text in patch.items():
            if (
                not isinstance(text, str)
                or len(text) > (120 if key == "name" else 4000)
                or (key == "name" and not text.strip())
            ):
                raise DomainError(422, "VALIDATION_ERROR", "invalid patch")
        hashed = hashlib.sha256(canonical(value).encode()).hexdigest()
        route = "PATCH /subscriptions/" + subscription_id
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM public_receipts WHERE actor_id=? AND route=? AND key=?",
                (actor.user_id, route, idempotency_key),
            ).fetchone()
            if previous:
                if previous["body_hash"] != hashed:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "idempotency conflict")
                data = json.loads(previous["response"])
                db.execute("COMMIT")
                return reply(request, data, etag=data["revision"])
            row = by_sub(subscription_id, db)
            if row["revision"] != rev:
                raise DomainError(409, "VERSION_CONFLICT", "revision changed")
            db.execute(
                "UPDATE projects SET name=?,notes=?,revision=revision+1,updated_at=? WHERE subscription_id=?",
                (
                    patch.get("name", row["name"]),
                    patch.get("notes", row["notes"]),
                    time.time(),
                    subscription_id,
                ),
            )
            data = subscription(store, by_sub(subscription_id, db), db=db,fresh_seconds=cfg.remote_fresh_seconds)
            commands.change(db, "tracking.subscription.updated", data)
            db.execute(
                "INSERT INTO public_receipts(actor_id,route,key,body_hash,response,created_at) VALUES(?,?,?,?,?,?)",
                (actor.user_id, route, idempotency_key, hashed, canonical(data), time.time()),
            )
            db.execute("COMMIT")
            return reply(request, data, etag=data["revision"])

    @app.get("/internal/v1/latest", dependencies=[Depends(service)])
    def latest(request: Request):
        return reply(request, page(store, "latest", dict(request.query_params)))

    @app.get("/internal/v1/activities", dependencies=[Depends(service)])
    def activities(request: Request):
        return reply(request, page(store, "activities", dict(request.query_params)))

    @app.get("/internal/v1/outbox", dependencies=[Depends(service)])
    def outbox(request: Request):
        with store.connect() as db:
            rows = [
                {
                    "event_id": r["event_id"],
                    "state": r["state"],
                    "error_code": r["error_code"],
                    "updated_at": r["updated_at"],
                }
                for r in db.execute("SELECT * FROM tracking_outbox ORDER BY updated_at LIMIT 100")
            ]
        return reply(request, {"items": rows, "next_cursor": None})

    @app.get("/internal/v1/status", dependencies=[Depends(service)])
    def status(request: Request):
        runtime = store.runtime()
        with store.connect() as db:
            meta = dict(
                db.execute(
                    "SELECT semantic_revision,clock_anomaly FROM feed_meta WHERE singleton=1"
                ).fetchone()
            )
            high_water = db.execute("SELECT COALESCE(MAX(first_seq),0) FROM tweet_ledger").fetchone()[0]
            job = db.execute(
                "SELECT state FROM retention_jobs ORDER BY created_at_ms DESC LIMIT 1"
            ).fetchone()
        return reply(
            request,
            {
                "service": "tracking",
                "schema_version": 4,
                "policy_version": feed.POLICY,
                "published_profile": feed.PROFILE,
                "semantic_revision": meta["semantic_revision"],
                "ledger_high_water": high_water,
                "retention_state": "clock_anomaly"
                if meta["clock_anomaly"]
                else job[0]
                if job
                else "scheduled",
                "external_collection_enabled": cfg.remote_enabled,
                "source_state": "unconfigured" if not cfg.remote_enabled else "not_verified",
                "alive": bool(runtime["heartbeat"] and time.time() - runtime["heartbeat"] < 10),
                "connection": runtime["connection"]
                if runtime["heartbeat"] and time.time() - runtime["heartbeat"] < 10
                else "disconnected",
            },
        )

    @app.get("/internal/v1/events", dependencies=[Depends(service)])
    async def events(request: Request):
        previous = request.headers.get("last-event-id")
        after = 0
        if previous:
            with store.connect() as db:
                from .retention import retention_now

                now = retention_now(db)
                old = db.execute(
                    "SELECT seq FROM changes WHERE event_id=? AND (json_extract(data,'$.tweet_id') IS NULL OR EXISTS(SELECT 1 FROM tweet_ledger l WHERE l.tweet_id=json_extract(changes.data,'$.tweet_id') AND l.expires_at_ms>? AND l.state!='expired'))",
                    (previous, now),
                ).fetchone()
                if old is None:
                    raise DomainError(422, "VALIDATION_ERROR", "unknown event cursor")
                after = old[0]

        with store.connect() as db:
            live_after = db.execute("SELECT COALESCE(MAX(seq),0) FROM changes").fetchone()[0]

        async def frames():
            nonlocal after
            heartbeat = 0
            while not await request.is_disconnected():
                with store.connect() as db:
                    from .retention import retention_now

                    now = retention_now(db)
                    rows = db.execute(
                        "SELECT * FROM changes WHERE seq>? AND (json_extract(data,'$.tweet_id') IS NULL OR EXISTS(SELECT 1 FROM tweet_ledger l WHERE l.tweet_id=json_extract(changes.data,'$.tweet_id') AND l.expires_at_ms>? AND l.state!='expired')) ORDER BY seq LIMIT 100",
                        (after, now),
                    ).fetchall()
                for row in rows:
                    after = row["seq"]
                    data = json.loads(row["data"])
                    if row["event_type"].startswith("tracking.feed.activity.") and row["seq"] <= live_after:
                        data = {**data, "replay": True, "is_live_new": False}
                    yield (
                        "id: "
                        + row["event_id"]
                        + "\nevent: "
                        + row["event_type"]
                        + "\ndata: "
                        + canonical({"data": data, "request_id": request.state.request_id})
                        + "\n\n"
                    )
                if time.monotonic() - heartbeat >= 15:
                    heartbeat = time.monotonic()
                    yield (
                        "event: heartbeat\ndata: "
                        + canonical({"data": {"scope": "ikun-main"}, "request_id": request.state.request_id})
                        + "\n\n"
                    )
                await asyncio.sleep(0.25)

        return StreamingResponse(frames(), media_type="text/event-stream")

    return app
