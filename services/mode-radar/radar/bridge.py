"""Loopback read-only snapshot and SSE bridge.

The website is the only intended client. This server binds 127.0.0.1, requires a
shared bearer token, and never accepts a URL, file path, or webhook from the caller.
A fresh SSE connection does not replay history. Last-Event-ID resumes after that id.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core.sanitize import redact, safe_https
from .coverage import coverage_report

PUBLIC_HOSTS = {
    "bscscan.com", "testnet.bscscan.com", "github.com", "docs.flap.sh",
    "four-meme.gitbook.io", "raw.githubusercontent.com",
}
FORBIDDEN_PORTS = {80, 443, 8443, 4000, 8545, 3311, 3322}


def bridge_settings(env):
    host = env.get("RADAR_BRIDGE_HOST") or "127.0.0.1"
    if host not in {"127.0.0.1", "::1"}:
        raise RuntimeError("雷达桥接只能监听本机回环")
    try:
        port = int(env.get("RADAR_BRIDGE_PORT") or "3921")
    except ValueError as exc:
        raise RuntimeError("雷达桥接端口无效") from exc
    if port in FORBIDDEN_PORTS or not (1024 <= port <= 65535):
        raise RuntimeError("雷达桥接端口与网站、隧道或钱包 RPC 冲突")
    token = env.get("RADAR_BRIDGE_TOKEN") or ""
    if len(token) < 32:
        raise RuntimeError("雷达桥接需要 RADAR_BRIDGE_TOKEN（至少 32 位），拒绝无认证监听")
    return host, port, token


def _event_row(row):
    url = safe_https(row["url"] or "", PUBLIC_HOSTS)
    payload_raw = row["payload"] or "{}"
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}
    safe_payload = {}
    if isinstance(payload, dict):
        for key, value in list(payload.items())[:8]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_payload[str(key)[:40]] = redact(value, 160) if isinstance(value, str) else value
    return {
        "id": int(row["id"]),
        "ts": int(row["ts"]),
        "source": redact(row["source"] or "", 80),
        "key": redact(row["key"] or "", 180),
        "kind": row["kind"] if row["kind"] in {"new", "changed", "gone", "baseline"} else "changed",
        "level": row["level"] if row["level"] in {"info", "warn", "crit"} else "info",
        "title": redact(row["title"] or "", 240),
        "detail": redact(row["detail"] or "", 400),
        "url": url,
        "payload": safe_payload,
    }


def snapshot(cfg, state, started_at):
    now = int(time.time())
    chains = {}
    onchain = ((cfg.get("probes") or {}).get("onchain") or {}).get("chains") or {}
    for name in onchain:
        chains[name] = {
            "mode": state.get_meta(f"chain_mode:{name}") or "unconfigured",
            "link": state.get_meta(f"chain_link:{name}") or state.get_meta(f"chain_mode:{name}") or "unconfigured",
            "detail": redact(state.get_meta(f"chain_detail:{name}") or "", 180),
            "head": state.get_meta(f"head:{name}") or "",
            "head_ts": int(state.get_meta(f"head_ts:{name}") or 0),
        }
    probes = {}
    for name in ("docs", "github", "schema", "onchain"):
        probes[name] = {
            "ok_ts": int(state.get_meta(f"probe_ok_ts:{name}") or 0),
            "error": redact(state.get_meta(f"probe_error:{name}") or "", 180),
        }
    rows = [_event_row(row) for row in state.recent_events(40)]
    return {
        "version": "0.2.0-ikun",
        "generated_at": now,
        "started_at": int(started_at),
        "bridge": "ok",
        "sample": False,
        "chains": chains,
        "probes": probes,
        "coverage": coverage_report(cfg, state),
        "events": rows,
        "latest_event_id": state.max_event_id(),
    }


class Bridge:
    def __init__(self, cfg, state, env, started_at=None):
        self.cfg = cfg
        self.state = state
        self.host, self.port, self.token = bridge_settings(env)
        self.started_at = started_at or time.time()
        self._httpd = None
        self._thread = None

    def start(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                return

            def _deny(self):
                body = b'{"error":"unauthorized"}'
                self.send_response(401)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.send_header("cache-control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _ok_auth(self):
                given = self.headers.get("Authorization") or ""
                expect = "Bearer " + bridge.token
                if len(given) != len(expect):
                    return False
                return hmac.compare_digest(given, expect)

            def do_GET(self):  # noqa: N802
                if not self._ok_auth():
                    self._deny()
                    return
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    self._json({"ok": True, "bridge": "ok"})
                elif path == "/v1/snapshot":
                    self._json(snapshot(bridge.cfg, bridge.state, bridge.started_at))
                elif path == "/v1/events":
                    self._events()
                else:
                    self.send_error(404)

            def _json(self, payload):
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.send_header("cache-control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _events(self):
                header = self.headers.get("Last-Event-ID") or ""
                latest = bridge.state.max_event_id()
                if header == "":
                    cursor = latest
                    replay = False
                elif header.isdigit():
                    cursor = int(header)
                    replay = True
                else:
                    body = b'{"error":"bad cursor"}'
                    self.send_response(422)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream; charset=utf-8")
                self.send_header("cache-control", "no-store")
                self.send_header("x-accel-buffering", "no")
                self.end_headers()
                hello = json.dumps({"cursor": cursor, "replay": replay}, ensure_ascii=False)
                self.wfile.write(f"event: hello\ndata: {hello}\n\n".encode())
                self.wfile.flush()
                idle = 0
                while True:
                    rows = bridge.state.events_after(cursor, 50)
                    if not rows:
                        idle += 1
                        try:
                            self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionError, OSError):
                            return
                        time.sleep(1)
                        if idle > 3600:
                            return
                        continue
                    idle = 0
                    for row in rows:
                        item = _event_row(row)
                        cursor = item["id"]
                        blob = json.dumps(item, ensure_ascii=False)
                        try:
                            self.wfile.write(f"id: {cursor}\nevent: radar\ndata: {blob}\n\n".encode())
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionError, OSError):
                            return

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="radar-bridge", daemon=True)
        self._thread.start()

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
