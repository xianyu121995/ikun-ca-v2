from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path = Path("data/tracking.db")
    remote_enabled: bool = False
    dedicated_account: bool = False
    watch_group: str = "ikun-ca-v2-project-tracking"
    token_file: str = ""
    admin_token_file: str = ""
    read_token_file: str = ""
    admin_subject: str = "superadmin"
    reconcile_seconds: float = 10
    backfill_seconds: float = 60
    request_interval: float = 0.5
    heartbeat_seconds: float = 15
    heartbeat_timeout: float = 10
    remote_fresh_seconds: float = 45
    host: str = "127.0.0.1"
    port: int = 3112
    auth_session_url: str = ""
    auth_origin: str = "https://ikun.ca"
    auth_cookie_name: str = "__Host-ikun_session"

    def secret(self, kind: str) -> str:
        env = {
            "token": "IKUN_TRACKING_6551_TOKEN",
            "admin_token": "IKUN_TRACKING_ADMIN_TOKEN",
            "read_token": "IKUN_TRACKING_READ_TOKEN",
        }[kind]
        path = getattr(self, f"{kind}_file")
        if path:
            p = Path(path)
            if p.stat().st_mode & 0o077:
                raise ValueError(f"{kind}_file must have mode 600")
            return p.read_text().strip()
        return os.environ.get(env, "").strip()

    @classmethod
    def load(cls, path: str) -> Config:
        p = Path(path).absolute()
        raw = json.loads(p.read_text())
        allowed = {f.name for f in fields(cls)}
        if raw.keys() - allowed:
            raise ValueError("unknown configuration fields")
        for name in ("db_path", "token_file", "admin_token_file", "read_token_file"):
            if raw.get(name):
                candidate = Path(raw[name])
                raw[name] = str(candidate if candidate.is_absolute() else p.parent / candidate)
        raw["db_path"] = Path(raw.get("db_path", p.parent / "data/tracking.db"))
        cfg = cls(**raw)
        if cfg.host != "127.0.0.1":
            raise ValueError("tracking service must bind to loopback")
        if cfg.auth_session_url:
            from urllib.parse import urlsplit

            target = urlsplit(cfg.auth_session_url)
            if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("auth session endpoint must use loopback HTTP")
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
        ):
            if getattr(cfg, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if cfg.remote_fresh_seconds < 2 * cfg.reconcile_seconds:
            raise ValueError("remote_fresh_seconds must cover at least two reconcile intervals")
        return cfg
