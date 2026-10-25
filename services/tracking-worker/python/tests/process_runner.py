"""Test-only local vendor injection. Production transport URLs are fixed in Remote/Worker."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages/runtime/python"))

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from websockets.asyncio.client import connect

from tracking.cli import serve as serve_tracking
from tracking.config import Config
from tracking.remote import Remote
from tracking.store import Store
from tracking.worker import Worker


async def main():
    cfg = Config.load(sys.argv[2])
    if sys.argv[1] == "website":
        app = FastAPI()

        @app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
        async def proxy(path: str, request: Request):
            async with httpx.AsyncClient() as client:
                upstream = await client.request(
                    request.method,
                    sys.argv[3] + "/" + path,
                    params=request.query_params,
                    content=await request.body(),
                    headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
                )
            return Response(
                upstream.content,
                upstream.status_code,
                headers={
                    k: v
                    for k, v in upstream.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
                },
            )

        await uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=cfg.port, access_log=False, log_level="error")
        ).serve()
        return
    store = Store(cfg.db_path)
    remote = Remote(cfg)
    remote.client.base_url = httpx.URL(sys.argv[3])
    worker = Worker(cfg, store, remote, ws_connect=lambda ignored, **kw: connect(sys.argv[4], **kw))
    await serve_tracking(cfg, worker=worker, log_level="error")


if __name__ == "__main__":
    asyncio.run(main())
