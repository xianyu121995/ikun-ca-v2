"""Turn untrusted probe text into something safe to store and show."""

from __future__ import annotations

import re

SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._\-]{8,}"
    r"|bot\d{5,}:[A-Za-z0-9_\-]{10,}"
    r"|sk-[A-Za-z0-9]{8,}"
    r"|wss://\S+"
    r"|https?://[^\s/]+:[^\s@]+@\S+"
    r"|RADAR_[A-Z0-9_]*(TOKEN|KEY|SECRET|WEBHOOK)\S*)"
)
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def redact(text: str, limit: int = 500) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = SECRET_RE.sub("[已隐藏]", CTRL_RE.sub(" ", text))
    cleaned = cleaned.replace("\u2028", " ").replace("\u2029", " ")
    return cleaned.strip()[:limit]


def safe_https(url: str, allowed_hosts: set[str] | None = None) -> str:
    """Keep only https links with no credentials. Optional host allow-list."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url.lower().startswith("https://") or any(c in url for c in "\r\n\t "):
        return ""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.username or parts.password or parts.scheme != "https":
        return ""
    host = (parts.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return ""
    if allowed_hosts is not None and not _host_ok(host, allowed_hosts):
        return ""
    return url[:500]


def _host_ok(host: str, allowed: set[str]) -> bool:
    return any(host == item or host.endswith("." + item) for item in allowed)
