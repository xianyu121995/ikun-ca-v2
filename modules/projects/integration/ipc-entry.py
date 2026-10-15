"""Pinned B0 entry: explicit migration or website-managed UDS only; no TCP listener."""
import argparse
import os
import re
import socket
import stat
import sys
import signal
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'candidate'))

from projects_service.ipc import IpcConfig,create_ipc_app
from projects_service.migration import FormalDatabase


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--migrate',action='store_true')
    parser.add_argument('--database')
    args=parser.parse_args()
    if args.migrate:
        FormalDatabase(args.database or os.environ['PROJECTS_DB']).migrate()
        print('PROJECTS_SCHEMA_2_READY')
        return
    config=IpcConfig.environment()
    path=Path(os.environ['IKUN_IPC_SOCKET'])
    parent=path.parent
    if not path.is_absolute() or len(os.fsencode(path))>100 or path.exists() or path.is_symlink() or parent.is_symlink():
        raise RuntimeError('UNSAFE_IPC_PATH')
    info=parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise RuntimeError('UNSAFE_IPC_DIRECTORY')
    FormalDatabase(config.database).inspect()
    import uvicorn
    class ManagedServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            # Uvicorn 0.54 replays SIGTERM after graceful shutdown. Suppress that replay
            # so the owned socket's inode cleanup below executes before process exit.
            previous={sig:signal.signal(sig,self.handle_exit) for sig in (signal.SIGTERM,signal.SIGINT)}
            try:yield
            finally:
                for sig,handler in previous.items():signal.signal(sig,handler)
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    listener.bind(str(path));os.chmod(path,0o600);listener.listen(128)
    original=path.stat().st_ino
    try:
        ManagedServer(uvicorn.Config(create_ipc_app(config),access_log=False,log_level='warning',
            timeout_keep_alive=5,timeout_graceful_shutdown=5,proxy_headers=False)).run(sockets=[listener])
    finally:
        listener.close()
        if path.exists() and path.stat().st_ino==original:path.unlink()


if __name__=='__main__':main()
