"""python -m hackathon.main --once | --loop | --doctor

One process. The website reads only the snapshot file.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from .binance_feed import discover_binance
from .engine import BEIJING, Store, canonical, clock, run_pass, source_kind
from .publish import build_site_snapshot, write_site_snapshot

HERE = Path(__file__).resolve().parents[1]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    if os.environ.get("HACKATHON_POLL_SECONDS"):
        cfg["poll_seconds"] = int(os.environ["HACKATHON_POLL_SECONDS"])
    cfg["poll_seconds"] = max(int(cfg.get("min_poll_seconds") or 300), int(cfg.get("poll_seconds") or 900))
    return cfg


def paths(args, cfg):
    db = args.db or os.environ.get("HACKATHON_DB") or cfg.get("db") or str(HERE / "data" / "hackathon.sqlite3")
    snapshot = args.snapshot or os.environ.get("HACKATHON_SNAPSHOT") or cfg.get("snapshot") or str(HERE / "data" / "snapshot.json")
    return db, snapshot


def install_manual(store: Store, cfg: dict):
    for item in cfg.get("manual_sources") or []:
        url = canonical(item["url"])
        kind = item.get("kind") or source_kind(url)
        if not kind:
            print(f"跳过不支持的手动来源 {url}", file=sys.stderr)
            continue
        event_id = item.get("event_id") or url
        store.add_source(event_id, url, kind, item.get("name") or url, chain=item.get("chain"), pinned=True)


def install_configured(store: Store, cfg: dict):
    """Install manual sources, then any pin the manual list does not already cover."""
    install_manual(store, cfg)
    covered = " ".join(str(item.get("url") or "") for item in cfg.get("manual_sources") or [])
    for item in cfg.get("pins") or []:
        if item.get("kind") == "binance_article" and item.get("code") and item["code"] not in covered:
            url = canonical(f"https://www.binance.com/en/support/announcement/detail/{item['code']}")
            store.add_source(item.get("event_id") or f"binance:{item['code']}", url, "binance-announcement",
                             item.get("name") or "Binance announcement", chain=item.get("chain") or "BSC", pinned=True)
        elif item.get("kind") == "bnb_blog" and item.get("slug") and item["slug"] not in covered:
            url = canonical(f"https://www.bnbchain.org/en/blog/{item['slug']}")
            store.add_source(item.get("event_id") or url, url, "bnb-news", item.get("name") or item["slug"],
                             chain=item.get("chain") or "BSC", pinned=True)


def _meta(store: Store, key: str):
    store.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row = store.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(store: Store, key: str, value: str):
    store.db.execute(
        "INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    store.db.commit()


def cycle(store: Store, cfg: dict, snapshot: str) -> int:
    timeout = int(cfg.get("request_timeout") or 20)
    completed_after = int(cfg.get("completed_refresh_seconds") or 6 * 3600)
    last = _meta(store, "completed_sweep")
    include_completed = True
    if last:
        try:
            include_completed = datetime.now(BEIJING) - datetime.fromisoformat(last) >= timedelta(seconds=completed_after)
        except ValueError:
            include_completed = True
    notices, failures = run_pass(
        store, "", timeout, skip_discovery=False, include_completed=include_completed,
        blog_pages=int(cfg.get("blog_pages_per_cycle") or 1),
    )
    if include_completed:
        _set_meta(store, "completed_sweep", clock().isoformat(timespec="seconds"))
    try:
        notices.extend(discover_binance(
            store,
            (cfg.get("sources") or {}).get("catalogs") or [93, 49],
            int(cfg.get("announcement_pages_per_cycle") or 3),
            timeout,
        ))
    except Exception as error:  # noqa: BLE001
        failures.append({"source": "binance-catalog", "error": str(error)})
    write_site_snapshot(snapshot, build_site_snapshot(store))
    print(json.dumps({"changes": len(notices), "failures": len(failures)}, ensure_ascii=False))
    for failure in failures:
        print(f"读取失败  {failure['source']}  {failure['error']}", file=sys.stderr)
    return 2 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ikun.ca 长期黑客松监控")
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--db")
    parser.add_argument("--snapshot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    mode.add_argument("--doctor", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    db, snapshot = paths(args, cfg)
    parent = os.path.dirname(os.path.abspath(db))
    os.makedirs(parent, exist_ok=True)
    store = Store(db)
    try:
        os.chmod(db, 0o600)
    except OSError:
        pass
    install_configured(store, cfg)
    if args.doctor:
        print("engine ok")
        return 0
    stop = False

    def request_stop(signum, _frame):
        nonlocal stop
        stop = True
        print(f"signal {signum}")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        if args.loop:
            import time
            while not stop:
                try:
                    cycle(store, cfg, snapshot)
                except Exception:
                    traceback.print_exc()
                slept = 0
                while slept < cfg["poll_seconds"] and not stop:
                    time.sleep(1)
                    slept += 1
            return 0
        return cycle(store, cfg, snapshot)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
