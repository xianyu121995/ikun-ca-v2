import asyncio
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from conftest import add, event, tweet
from websockets.asyncio.server import serve

from tracking.store import Store


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def until(fn, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = await fn()
            if value:
                return value
        except (httpx.HTTPError, AssertionError):
            pass
        await asyncio.sleep(0.05)
    raise AssertionError("local process condition timed out")


async def test_website_shutdown_restart_and_worker_crash_recovery(tmp_path, cfg, store, vendor):
    add(store)
    peers = set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            response = vendor(httpx.Request("POST", "https://ai.6551.io" + self.path, content=body))
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def websocket(ws):
        peers.add(ws)
        try:
            async for raw in ws:
                await ws.send("pong" if raw == "ping" else json.dumps({"id": 1, "result": {"success": True}}))
        finally:
            peers.discard(ws)

    engine_port, site_port = free_port(), free_port()
    engine_config, site_config = tmp_path / "engine.json", tmp_path / "site.json"
    engine_config.write_text(
        json.dumps(
            {
                "db_path": str(cfg.db_path),
                "remote_enabled": True,
                "dedicated_account": True,
                "port": engine_port,
                "reconcile_seconds": 0.1,
                "backfill_seconds": 60,
                "request_interval": 0,
                "heartbeat_seconds": 0.1,
                "heartbeat_timeout": 0.5,
            }
        )
    )
    site_config.write_text(json.dumps({"port": site_port}))
    processes = []
    runner = str(Path(__file__).with_name("process_runner.py"))
    log = tmp_path / "process.log"

    async def spawn(*args):
        with log.open("ab") as out:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                runner,
                *args,
                stdout=out,
                stderr=out,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            )
        processes.append(process)
        return process

    async def stop(process, crash=False):
        if process.returncode is None:
            process.kill() if crash else process.terminate()
            await asyncio.wait_for(process.wait(), 10)

    engine_url, site_url = f"http://127.0.0.1:{engine_port}", f"http://127.0.0.1:{site_port}"
    try:
        async with serve(websocket, "127.0.0.1", 0) as wss, httpx.AsyncClient() as client:
            wss_url = "ws://127.0.0.1:" + str(wss.sockets[0].getsockname()[1])
            engine_args = ("engine", str(engine_config), f"http://127.0.0.1:{server.server_port}", wss_url)
            engine = await spawn(*engine_args)
            site = await spawn("website", str(site_config), engine_url)

            async def healthy():
                response = await client.get(site_url + "/healthz")
                return (
                    response.status_code == 200
                    and store.get("prj_550e8400-e29b-41d4-a716-446655440001")["remote_state"] == "active"
                    and bool(peers)
                )

            await until(healthy)
            assert (await client.get(site_url + "/health/live")).status_code == 200
            await stop(site)
            t = tweet(tweet_id="777")
            for peer in list(peers):
                await peer.send(json.dumps(event(t)))

            async def received():
                return len(store.activities()) == 1

            await until(received)
            assert engine.returncode is None  # Site process is gone, engine still commits tweets.
            site = await spawn("website", str(site_config), engine_url)
            await until(healthy)
            response = await client.get(
                site_url + "/internal/v1/latest",
                headers={"Authorization": "Bearer " + os.environ["TRACKING_API_TOKEN"]},
            )
            assert response.json()["data"]["items"][0]["tweet_id"] == "777"
            await stop(engine, crash=True)
            # Production launchd's 30s throttle outlasts the 30s SQLite lease. Simulate expiry, no wall-clock wait.
            store.runtime(heartbeat=time.time() - 31)
            await until(lambda: asyncio.sleep(0.01, result=not peers))
            engine = await spawn(*engine_args)
            await until(healthy)
            for peer in list(peers):
                await peer.send(json.dumps(event(t)))
                await peer.send(json.dumps(event(tweet(tweet_id="778"))))
            await until(lambda: asyncio.sleep(0.01, result=len(store.activities()) == 2))
            assert [r["tweet_id"] for r in Store(cfg.db_path).activities()] == ["777", "778"]
            assert sum(endpoint == "twitter_watch_add" for endpoint, _ in vendor.calls) == 1
            await stop(engine)
            assert store.runtime()["heartbeat"] == 0
    finally:
        for process in processes:
            await stop(process)
        server.shutdown()
        server.server_close()


async def test_standalone_absolute_entry_from_private_cwd_ignores_development_imports(tmp_path):
    import shutil

    module = Path(__file__).resolve().parents[1]
    release = tmp_path / "standalone-release"
    released_module = release / "services/tracking-worker/python"
    released_module.mkdir(parents=True)
    shutil.copytree(
        module / "tracking", released_module / "tracking", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copyfile(module / "entry.py", released_module / "entry.py")
    shutil.copytree(module.parents[2] / "schemas/tracking", release / "schemas/tracking")
    job = tmp_path / "private-job"
    job.mkdir(mode=0o700)
    data = tmp_path / "standalone-data"
    config = job / "tracking.json"
    port = free_port()
    config.write_text(
        json.dumps(
            {
                "db_path": str(data / "tracking/tracking.db"),
                "port": port,
                "remote_enabled": False,
                "dedicated_account": False,
            }
        )
    )
    config.chmod(0o600)
    env = {
        "PATH": os.environ["PATH"],
        "DATA_ROOT": str(data),
        "TRACKING_API_TOKEN": "standalone-release-direction-xxxxxxxxxxxx",
        "PYTHONPATH": "/nonexistent-development-import",
        "IKUN_TRACKING_EXTERNAL_IO_DISABLED": "1",
    }
    init = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(released_module / "entry.py"),
        "init",
        "--config",
        str(config),
        cwd=job,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await init.communicate()
    assert init.returncode == 0, stderr.decode()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(released_module / "entry.py"),
        "serve",
        "--config",
        str(config),
        cwd=job,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def ready():
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{port}/health/ready")
            return response.json()["data"] if response.is_success else False

    try:
        health = await until(ready)
        assert health["external_collection_enabled"] is False and health["source_state"] == "unconfigured"
        assert not list(job.glob(".env*"))
    finally:
        process.terminate()
        await asyncio.wait_for(process.communicate(), 10)
    assert process.returncode == 0
