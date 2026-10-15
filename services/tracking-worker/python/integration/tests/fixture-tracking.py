"""Synthetic local provider. This entry is never imported by the production worker."""
# ruff: noqa: E402 -- this standalone fixture sets its test-only import roots before local imports.

import asyncio
import json
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MODULE), str(MODULE / "tests")]
import httpx
from conftest import Vendor
from fastapi import Request
from fastapi.responses import JSONResponse
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from tracking import cli
from tracking.api import create_app
from tracking.config import Config
from tracking.remote import Remote
from tracking.store import Store
from tracking.worker import Worker


async def main():
    cfg = Config.load(sys.argv[1])
    store = Store(cfg.db_path)
    vendor = Vendor()
    peers = set()
    active_streams = 0
    remote = Remote(cfg, transport=httpx.MockTransport(vendor))

    async def socket(ws):
        peers.add(ws)
        try:
            async for raw in ws:
                if raw == "ping":
                    await ws.send("pong")
                else:
                    await ws.send(json.dumps({"id": 1, "result": {"success": True}}))
        finally:
            peers.discard(ws)

    async with serve(socket, "127.0.0.1", 0) as wss:
        target = "ws://127.0.0.1:" + str(wss.sockets[0].getsockname()[1])
        worker = Worker(cfg, store, remote, ws_connect=lambda ignored, **kw: connect(target, **kw))
        app = create_app(cfg, store)

        async def allowed(request):
            return request.headers.get("x-fixture-token") == sys.argv[2]

        @app.post("/fixture/control")
        async def control(request: Request):
            if not await allowed(request):
                return JSONResponse({}, status_code=403)
            changes = await request.json()
            for key, value in changes.items():
                if key not in ("quota", "add_noop", "delete_noop", "list_fails", "uncertain_add"):
                    return JSONResponse({}, status_code=422)
                setattr(vendor, key, value)
            for row in store.projects(include_removed=True):
                store.observe(row, next_retry=0)
            return {"ok": True}

        @app.post("/fixture/emit")
        async def emit(request: Request):
            if not await allowed(request):
                return JSONResponse({}, status_code=403)
            body = await request.json()
            content = body["content"]
            username = body.get("username", "project1")
            vendor.tweets.append(content)
            packet = {
                "method": "twitter.event",
                "params": {
                    "twAccount": username,
                    "eventType": body.get("event_type", "NEW_TWEET"),
                    "content": content,
                },
            }
            for ws in list(peers):
                await ws.send(json.dumps(packet))
            return {"ok": True}

        @app.get("/fixture/state")
        async def state(request: Request):
            if not await allowed(request):
                return JSONResponse({}, status_code=403)
            return {
                "active_streams": active_streams,
                "peers": len(peers),
                "watches": list(vendor.rows),
                "add_calls": sum(k == "twitter_watch_add" for k, _ in vendor.calls),
                "delete_calls": sum(k == "twitter_watch_delete" for k, _ in vendor.calls),
            }

        class Observed:
            async def __call__(self, scope, receive, send):
                nonlocal active_streams
                streaming = scope["type"] == "http" and scope["path"] == "/internal/v1/events"
                if streaming:
                    active_streams += 1
                try:
                    await app(scope, receive, send)
                finally:
                    if streaming:
                        active_streams -= 1

        cli.create_app = lambda ignored: Observed()
        await cli.serve(cfg, worker=worker, log_level="warning")


if __name__ == "__main__":
    asyncio.run(main())
