from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from contextlib import contextmanager

import uvicorn

from .api import create_app
from .config import Config
from .remote import Remote
from .store import Store
from .worker import Worker


async def run_worker(cfg):
    worker = Worker(cfg, Store(cfg.db_path), Remote(cfg))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop.set)
    await worker.run()


class ApiServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # Coordinate shutdown of both tasks before the process exits.
        yield


async def serve(cfg, *, worker=None, log_level="warning"):
    worker = worker or Worker(cfg, Store(cfg.db_path), Remote(cfg))
    server = ApiServer(
        uvicorn.Config(create_app(cfg), host=cfg.host, port=cfg.port, access_log=False, log_level=log_level)
    )
    loop = asyncio.get_running_loop()

    def shutdown():
        worker.stop.set()
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
    tasks = [asyncio.create_task(worker.run()), asyncio.create_task(server.serve())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        worker.stop.set()
        server.should_exit = True
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
        except TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description="Independent ikun.ca NEW_TWEET monitoring")
    parser.add_argument("command", choices=("serve", "api", "worker", "init", "migrate"))
    parser.add_argument("--config", default="config.local.json")
    args = parser.parse_args()
    cfg = Config.load(args.config)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # HTTP/WebSocket library diagnostics can contain authentication-bearing URLs.
    for name in ("httpx", "httpcore", "websockets"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    if args.command == "serve":
        asyncio.run(serve(cfg))
    elif args.command == "api":
        uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, access_log=False)
    elif args.command == "worker":
        asyncio.run(run_worker(cfg))
    else:
        Store(cfg.db_path, initialize=True)
        print("tracking.db initialized; no remote requests made")


if __name__ == "__main__":
    main()
