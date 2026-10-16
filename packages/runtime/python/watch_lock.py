"""Serialize 6551 capacity checks and mutations across the two v2 workers."""
import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

@asynccontextmanager
async def watch_lock(database):
    path = Path(database).parent.parent / '.6551-watch.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    deadline = time.monotonic() + 30
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('watch_lock_timeout')
                await asyncio.sleep(.1)
        yield
    finally:
        os.close(fd)
