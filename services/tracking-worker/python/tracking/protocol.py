"""Strict frozen B2 wire. Human identity is verified by B1 in the website, not stored here."""

import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
SCOPE = "ikun-main"


def utc(at=None):
    return datetime.fromtimestamp(at, UTC).isoformat().replace("+00:00", "Z") if at is not None else None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class DomainError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Principal(Strict):
    user_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    tenant_id: Literal["ikun-main"]
    role: Literal["superadmin", "user"]


class Target(Strict):
    name: str = Field(min_length=1, max_length=120)
    x_user_id: str | None = Field(pattern=r"^[0-9]{1,40}$")
    x_handle: str = Field(pattern=r"^[A-Za-z0-9_]{1,15}$")
    notes: str = Field(max_length=4000)
    confirmed: Literal[True]

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("nonblank name required")
        return value

    @field_validator("confirmed", mode="before")
    @classmethod
    def human(cls, value):
        if value is not True:
            raise ValueError("explicit human confirmation required")
        return value


class Command(Strict):
    schema_version: Literal[1]
    command_id: str = Field(pattern="^cmd_" + UUID4 + "$")
    tenant_id: Literal["ikun-main"]
    actor: Principal
    operation: Literal[
        "tracking.create", "tracking.start", "tracking.stop", "tracking.resume", "tracking.remove"
    ]
    project_id: str = Field(pattern="^prj_" + UUID4 + "$")
    subscription_id: str | None = Field(pattern="^sub_" + UUID4 + "$")
    expected_revision: StrictInt | None = Field(ge=1)
    payload: dict
    issued_at: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def version(cls, value):
        if type(value) is not int:
            raise ValueError("invalid schema version")
        return value

    @field_validator("issued_at")
    @classmethod
    def timestamp(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)", value):
            raise ValueError("UTC required")
        datetime.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def semantics(self):
        if self.actor.role != "superadmin":
            raise DomainError(403, "FORBIDDEN", "superadmin required")
        if self.operation == "tracking.create":
            self.payload = Target.model_validate(self.payload).model_dump()
            self.payload["x_handle"] = self.payload["x_handle"].lower()
            if self.subscription_id is not None or self.expected_revision is not None:
                raise ValueError("create reference mismatch")
        elif self.subscription_id is None or self.expected_revision is None or self.payload:
            raise ValueError("subscription, revision and empty payload required")
        return self
