from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal

import uvicorn

from .config import Settings
from .store import Store


def main():
    parser = argparse.ArgumentParser(description='Independent HunterRadar service; owns hunter.db only')
    parser.add_argument('command', choices=('run','api','worker','status','init'), nargs='?', default='run')
    args = parser.parse_args()
    settings = Settings.load()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # Keep HTTP library diagnostics from printing bearer/query tokens.
    for name in ('httpx','httpcore','websockets'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    store = Store(settings.db)
    if args.command in ('status','init'):
        print(json.dumps(store.status(), ensure_ascii=False, indent=2))
    elif args.command == 'worker':
        from .engine import Engine
        async def work():
            engine = Engine(settings, store)
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, engine.stop.set)
            await engine.run()
        asyncio.run(work())
    else:
        from .api import create_app
        uvicorn.run(create_app(settings, worker=args.command=='run', store=store), host=settings.host,
                    port=settings.port, proxy_headers=False, access_log=False, workers=1)


if __name__ == '__main__':
    main()
