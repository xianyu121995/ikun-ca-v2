"""python -m hackathon.main --once | --loop | --doctor"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import traceback
from pathlib import Path

from .collect import run_cycle
from .http_client import HttpClient
from .snapshot import build_snapshot, write_snapshot
from .store import Store

HERE = Path(__file__).resolve().parents[1]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    if os.environ.get("HACKATHON_POLL_SECONDS"):
        cfg["poll_seconds"] = int(os.environ["HACKATHON_POLL_SECONDS"])
    cfg["poll_seconds"] = max(int(cfg.get("min_poll_seconds") or 300), int(cfg.get("poll_seconds") or 1800))
    return cfg


def paths(args, cfg):
    db = args.db or os.environ.get("HACKATHON_DB") or cfg.get("db") or str(HERE / "data" / "hackathon.sqlite3")
    snapshot = args.snapshot or os.environ.get("HACKATHON_SNAPSHOT") or cfg.get("snapshot") or str(HERE / "data" / "snapshot.json")
    return db, snapshot


def publish(store, snapshot_path):
    write_snapshot(snapshot_path, build_snapshot(store))


def doctor(cfg, client) -> int:
    url = cfg["sources"]["hackathon_index"]
    try:
        status, body = client.fetch(url)
        ok = status == 200 and b"hackathonPrograms" in body
        print(f"index {'ok' if ok else 'fail'} HTTP {status} {len(body)} bytes")
        return 0 if ok else 1
    except Exception as error:  # noqa: BLE001
        print(f"index fail {type(error).__name__}")
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="长期运行的 BNB Chain / BSC 官方黑客松监控")
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--db")
    parser.add_argument("--snapshot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    mode.add_argument("--doctor", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    client = HttpClient(gap=float(cfg.get("request_gap_seconds") or 0.8))
    if args.doctor:
        return doctor(cfg, client)
    db, snapshot = paths(args, cfg)
    store = Store(db)
    stop = False

    def request_stop(signum, _frame):
        nonlocal stop
        stop = True
        print(f"signal {signum}, finishing this cycle")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        if args.loop:
            import time
            while not stop:
                _cycle(cfg, client, store, snapshot)
                slept = 0
                while slept < cfg["poll_seconds"] and not stop:
                    time.sleep(1)
                    slept += 1
            return 0
        report = _cycle(cfg, client, store, snapshot)
        useful = report["index"] or report["details"] or report["blog"] or report["announcements"]
        print(json.dumps(report, ensure_ascii=False))
        return 0 if useful else 1
    finally:
        store.close()


def _cycle(cfg, client, store, snapshot) -> dict:
    try:
        report = run_cycle(cfg, client, store)
    except Exception:
        traceback.print_exc()
        report = {"index": 0, "details": 0, "blog": 0, "announcements": 0, "errors": ["cycle"]}
    publish(store, snapshot)
    return report


if __name__ == "__main__":
    sys.exit(main())
