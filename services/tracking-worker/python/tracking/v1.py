"""Versioned single-site API adapter; shared contract changes remain reviewable in this module."""

import base64
import json
import re
import secrets
import sqlite3
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .store import Conflict, Missing


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: str = Field(
        pattern=r"^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    name: str = Field(min_length=1, max_length=200)
    handle: str = Field(min_length=1, max_length=16)
    notes: str = Field(default="", max_length=4000)
    confirmed: Literal[True]


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


def utc(value):
    dates = {
        "observed_at",
        "confirmed_at",
        "created_at",
        "updated_at",
        "received_at",
        "next_retry",
        "last_heartbeat",
        "last_pong",
        "last_tweet_at",
    }
    if isinstance(value, dict):
        return {
            k: (datetime.fromtimestamp(v, UTC).isoformat().replace("+00:00", "Z") if v else None)
            if k in dates
            else utc(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [utc(v) for v in value]
    return value


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def decode(value):
    try:
        return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, TypeError):
        raise HTTPException(422, "invalid cursor") from None


def install(app, store, actor, admin, project, engine):
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def reply(data, request, *, status=200, revision=None):
        headers = {"ETag": f'"rev-{revision}"'} if revision else {}
        return JSONResponse(
            {"data": utc(data), "request_id": request.state.request_id}, status_code=status, headers=headers
        )

    @api.middleware("http")
    async def request_id(request, next_call):
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else secrets.token_hex(16)
        )
        response = await next_call(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @api.exception_handler(HTTPException)
    @api.exception_handler(Conflict)
    @api.exception_handler(Missing)
    @api.exception_handler(ValueError)
    @api.exception_handler(RequestValidationError)
    @api.exception_handler(sqlite3.Error)
    async def error(request, exc):
        if isinstance(exc, HTTPException):
            status, message = exc.status_code, str(exc.detail)
        elif isinstance(exc, Conflict):
            status, message = 409, str(exc)
        elif isinstance(exc, Missing):
            status, message = 404, "subscription not found"
        elif isinstance(exc, sqlite3.Error):
            status, message = 503, "tracking storage unavailable"
        else:
            status, message = 422, "invalid request fields"
        code = {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            428: "VALIDATION_ERROR",
            503: "DB_UNAVAILABLE",
        }.get(status, "VALIDATION_ERROR")
        if status == 409:
            code = (
                "IDEMPOTENCY_CONFLICT"
                if "idempotency" in message
                else "VERSION_CONFLICT"
                if "revision" in message
                else code
            )
        return JSONResponse(
            {
                "error": {"code": code, "message": message, "retryable": isinstance(exc, sqlite3.Error)},
                "request_id": request.state.request_id,
            },
            status_code=status,
        )

    def idem(idempotency_key: UUID = Header()):
        return str(idempotency_key)

    def revision(if_match: str | None = Header(default=None)):
        if if_match is None:
            raise HTTPException(428, "If-Match required")
        match = re.fullmatch(r'"rev-([1-9][0-9]*)"', if_match)
        if not match:
            raise HTTPException(422, "invalid If-Match")
        return int(match[1])

    @api.get("/status")
    def status(request: Request, user=Depends(actor)):
        return reply({"engine": engine()}, request)

    @api.get("/subscriptions")
    def listing(
        request: Request,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=100),
        include_removed: bool = False,
        user=Depends(actor),
    ):
        rows = sorted(store.projects(include_removed), key=lambda row: (row["updated_at"], row["project_id"]))
        if cursor:
            previous = decode(cursor)
            if (
                not isinstance(previous, list)
                or len(previous) != 2
                or not isinstance(previous[0], (int, float))
                or not isinstance(previous[1], str)
            ):
                raise HTTPException(422, "invalid cursor")
            rows = [r for r in rows if (r["updated_at"], r["project_id"]) > tuple(previous)]
        selected = rows[:limit]
        next_cursor = (
            encode([selected[-1]["updated_at"], selected[-1]["project_id"]]) if len(rows) > limit else None
        )
        return reply({"items": [project(r) for r in selected], "next_cursor": next_cursor}, request)

    @api.post("/subscriptions")
    def create(body: Create, request: Request, user=Depends(admin), key=Depends(idem)):
        row = store.mutate("create", body.project_id, body.model_dump(), user.subject, key)
        return reply(project(row), request, status=201, revision=row["revision"])

    @api.get("/subscriptions/{project_id}")
    def detail(project_id: str, request: Request, user=Depends(actor)):
        row = store.get(project_id)
        return reply(project(row), request, revision=row["revision"])

    @api.patch("/subscriptions/{project_id}")
    def update(
        project_id: str,
        body: Patch,
        request: Request,
        user=Depends(admin),
        key=Depends(idem),
        rev=Depends(revision),
    ):
        row = store.mutate(
            "update",
            project_id,
            {**body.model_dump(exclude_none=True), "expected_revision": rev},
            user.subject,
            key,
        )
        return reply(project(row), request, revision=row["revision"])

    @api.delete("/subscriptions/{project_id}")
    def remove(
        project_id: str, request: Request, user=Depends(admin), key=Depends(idem), rev=Depends(revision)
    ):
        row = store.mutate("remove", project_id, {"expected_revision": rev}, user.subject, key)
        return reply(project(row), request, status=202, revision=row["revision"])

    @api.post("/subscriptions/{project_id}/{operation}")
    def command(
        project_id: str,
        operation: Literal["start", "stop", "resume"],
        request: Request,
        user=Depends(admin),
        key=Depends(idem),
        rev=Depends(revision),
    ):
        row = store.mutate(operation, project_id, {"expected_revision": rev}, user.subject, key)
        return reply(project(row), request, status=202, revision=row["revision"])

    @api.get("/latest")
    def latest(
        request: Request,
        project_id: str | None = None,
        limit: int = Query(50, ge=1, le=100),
        user=Depends(actor),
    ):
        return reply({"items": store.latest(project_id, limit)}, request)

    @api.get("/activities")
    def activities(
        request: Request,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int = Query(50, ge=1, le=100),
        user=Depends(actor),
    ):
        after = decode(cursor) if cursor else 0
        if type(after) is not int or after < 0:
            raise HTTPException(422, "invalid cursor")
        rows = store.activities(project_id, after, limit)
        return reply({"items": rows, "next_cursor": encode(rows[-1]["seq"]) if rows else cursor}, request)

    app.mount("/api/v1/tracking", api)
