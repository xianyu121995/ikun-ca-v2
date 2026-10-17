from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path = Path("data/tracking/tracking.db")
    remote_enabled: bool = False
    dedicated_account: bool = False
    shared_account_safe: bool = False
    watch_group: str = "ikun-ca-v2-project-tracking"
    token_file: str = ""
    admin_token_file: str = ""
    read_token_file: str = ""
    admin_subject: str = "superadmin"
    reconcile_seconds: float = 10
    backfill_seconds: float = 60
    request_interval: float = 0.5
    heartbeat_seconds: float = 3
    heartbeat_timeout: float = 10
    remote_fresh_seconds: float = 45
    host: str = "127.0.0.1"
    port: int = 3112
    auth_session_url: str = ""
    auth_origin: str = "https://ikun.ca"
    auth_cookie_name: str = "__Host-ikun_session"
    service_token_file: str = ""
    max_watch_slots: int = 600
    shared_watch_ids: dict[str, str] | None = None
    adopted_watch_ids: dict[str, str] | None = None

    def secret(self, kind: str) -> str:
        env = {
            "token": "IKUN_TRACKING_6551_TOKEN",
            "admin_token": "IKUN_TRACKING_ADMIN_TOKEN",
            "read_token": "IKUN_TRACKING_READ_TOKEN",
            "service_token": "TRACKING_API_TOKEN",
        }[kind]
        path = getattr(self, f"{kind}_file")
        if path:
            p = Path(path)
            if p.stat().st_mode & 0o077:
                raise ValueError(f"{kind}_file must have mode 600")
            value = p.read_text().strip()
        else:
            value = os.environ.get(env, "").strip()
        if len(value) > 8192 or any(not 33 <= ord(char) <= 126 for char in value):
            raise ValueError(f"invalid {kind} credential format")
        return value

    @classmethod
    def load(cls, path: str) -> Config:
        p = Path(path).absolute()
        raw = json.loads(p.read_text())
        allowed = {f.name for f in fields(cls)}
        if raw.keys() - allowed:
            raise ValueError("unknown configuration fields")
        for name in ("db_path", "token_file", "admin_token_file", "read_token_file", "service_token_file"):
            if raw.get(name):
                candidate = Path(raw[name])
                raw[name] = str(candidate if candidate.is_absolute() else p.parent / candidate)
        raw["db_path"] = Path(raw.get("db_path", p.parent / "data/tracking/tracking.db"))
        cfg = cls(**raw)
        if os.environ.get("IKUN_TRACKING_EXTERNAL_IO_DISABLED") == "1" and (
            cfg.remote_enabled or cfg.dedicated_account or cfg.token_file
        ):
            raise ValueError("this release requires external collection disabled")
        if cfg.auth_session_url or cfg.admin_token_file or cfg.read_token_file:
            raise ValueError("legacy human authentication configuration is retired; use website B1")
        if type(cfg.max_watch_slots) is not int or not 1 <= cfg.max_watch_slots <= 600:
            raise ValueError("NEW_TWEET capacity cannot exceed 600")
        if (
            os.environ.get("DATA_ROOT")
            and cfg.db_path.resolve() != (Path(os.environ["DATA_ROOT"]) / "tracking/tracking.db").resolve()
        ):
            raise ValueError("tracking db_path must match configured DATA_ROOT")
        if cfg.db_path.parent.name != "tracking":
            raise ValueError("tracking database must use DATA_ROOT/tracking/tracking.db")
        if cfg.host != "127.0.0.1":
            raise ValueError("tracking service must bind to loopback")
        if type(cfg.port) is not int or not 1 <= cfg.port <= 65535:
            raise ValueError("invalid tracking port")
        if type(cfg.remote_enabled) is not bool or type(cfg.dedicated_account) is not bool:
            raise ValueError("remote_enabled and dedicated_account must be booleans")
        if not cfg.watch_group.startswith("ikun-ca-v2-"):
            raise ValueError("watch_group must use isolated ikun-ca-v2- namespace")
        for name in (
            "reconcile_seconds",
            "backfill_seconds",
            "heartbeat_seconds",
            "heartbeat_timeout",
            "remote_fresh_seconds",
            "request_interval",
        ):
            value = getattr(cfg, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value < 0
                or (name != "request_interval" and value == 0)
            ):
                raise ValueError(f"invalid {name}")
        if cfg.remote_fresh_seconds < 2 * cfg.reconcile_seconds:
            raise ValueError("remote_fresh_seconds must cover at least two reconcile intervals")
        if cfg.shared_watch_ids is not None:
            import re
            if not isinstance(cfg.shared_watch_ids, dict) or any(
                not isinstance(k, str) or not re.fullmatch(r"[a-z0-9_]{1,15}", k)
                or not isinstance(v, str) or not v.isdigit()
                for k, v in cfg.shared_watch_ids.items()
            ):
                raise ValueError("invalid shared_watch_ids")
            if set(cfg.shared_watch_ids) & set(cfg.adopted_watch_ids or {}):
                raise ValueError("shared watches cannot be adopted")
        return cfg
