from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

import uvicorn

from .config import Settings
from .store import Store


def main():
    parser = argparse.ArgumentParser(description='Independent HunterRadar service; owns hunter.db only')
    parser.add_argument('command', choices=('run','api','worker','status','init','migrate','restore'), nargs='?', default='run')
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--destination',type=Path)
    parser.add_argument('--current',type=Path)
    args = parser.parse_args()
    settings = Settings.load()
    if args.command=='restore':
        if not args.bundle or not args.destination or not args.current:parser.error('restore requires --bundle, --destination and --current; stop source worker first')
        from .retention import restore_bundle
        print(json.dumps(restore_bundle(args.bundle,args.destination,current=args.current),ensure_ascii=False))
        return
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # Keep HTTP library diagnostics from printing bearer/query tokens.
    for name in ('httpx','httpcore','websockets'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    store = Store(settings.db,initialize=args.command in ('init','migrate'))
    if args.command in ('status','init','migrate'):
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
