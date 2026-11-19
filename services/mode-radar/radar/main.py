"""Entry point: python -m radar.main --once | --loop | --doctor"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import traceback

from .core.http import Http
from .core.notify import Notifier
from .core.state import State
from .probes.base import Ctx, Signal
from .probes.docs import DocsProbe
from .probes.github import GithubProbe
from .probes.onchain import OnchainProbe
from .probes.schema import SchemaProbe

PROBES = {
    "docs": DocsProbe,
    "github": GithubProbe,
    "schema": SchemaProbe,
    "onchain": OnchainProbe,
}

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "0.2.0-ikun"
_STOP = threading.Event()

# env var -> dotted config path. Secrets stay in /etc/mode-radar.env, not in git.
ENV_MAP = {
    "RADAR_WEBHOOK": "notify.webhook_url",
    "RADAR_TG_TOKEN": "notify.telegram.token",
    "RADAR_TG_CHAT": "notify.telegram.chat_id",
    "RADAR_MIN_LEVEL": "notify.min_level",
    "RADAR_PROXY": "http.proxy",
    "RADAR_GITHUB_TOKEN": "probes.github.token",
}


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    apply_env(cfg, os.environ)
    return cfg


def _set_path(cfg, dotted, value):
    parts = dotted.split(".")
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def apply_env(cfg, env):
    for var, dotted in ENV_MAP.items():
        if env.get(var):
            _set_path(cfg, dotted, env[var])
    chains = cfg.setdefault("probes", {}).setdefault("onchain", {}).setdefault("chains", {})
    if env.get("RADAR_WSS_BSC"):
        chains.setdefault("bsc", {})["wss"] = env["RADAR_WSS_BSC"].strip()
    if env.get("RADAR_RPC_BSC"):
        # HTTP RPC is not a substitute for WSS subscriptions. The value is not stored.
        chains.setdefault("bsc", {})["ignored_http_rpc"] = "ignored"
    if env.get("RADAR_ALLOW_EXTERNAL_NOTIFY") == "1":
        cfg.setdefault("notify", {})["allow_external"] = True
    return cfg


def build(cfg, db_path, only=None):
    hcfg = cfg.get("http") or {}
    http = Http(
        timeout=hcfg.get("timeout", 20),
        retries=hcfg.get("retries", 3),
        proxy=hcfg.get("proxy") or None,
    )
    state = State(db_path)
    notifier = Notifier(cfg.get("notify"), http, state)

    probes = []
    for name, cls in PROBES.items():
        pcfg = (cfg.get("probes") or {}).get(name)
        if pcfg is None:
            continue
        probe = cls(pcfg, http, state)
        if not probe.enabled:
            continue
        if only and name not in only:
            continue
        probes.append(probe)
    return http, state, notifier, probes


def run_probe(probe, ctx, state, notifier, timeout=None):
    """Run one probe under a watchdog so a hung HTTP call cannot stall the loop."""
    timeout = timeout or probe.cfg.get("timeout", 600)
    box = {}

    def work():
        try:
            box["signals"] = probe.run(ctx)
        except Exception:  # noqa: BLE001
            box["error"] = traceback.format_exc()

    t0 = time.time()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        ctx.log(f"[{probe.name}] 超时 {timeout}s，本轮跳过")
        state.set_meta(f"probe_error:{probe.name}", "timeout")
        return 0
    if "error" in box:
        ctx.log(f"[{probe.name}] 异常:\n{box['error']}")
        state.set_meta(f"probe_error:{probe.name}", "error")
        return 0
    state.set_meta(f"probe_error:{probe.name}", "")
    state.set_meta(f"probe_ok_ts:{probe.name}", int(time.time()))

    signals = box.get("signals") or []
    new = []
    for sig in signals:
        if state.emit(sig) is not None:
            new.append(sig)
    if new:
        notifier.send(new)
    ctx.log(f"[{probe.name}] {len(signals)} 条信号 / {len(new)} 条新告警  ({time.time() - t0:.1f}s)")
    return len(new)


# ---------------------------------------------------------------- doctor
def doctor(cfg, http):
    """Self-check every configured endpoint before trusting the service."""
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append((True, name, detail))
        except Exception as e:  # noqa: BLE001
            results.append((False, name, f"{type(e).__name__}: {e}"))

    probes = cfg.get("probes") or {}

    for t in (probes.get("docs") or {}).get("targets", []):
        def _docs(t=t):
            text = http.get_text(t["url"])
            from .probes.docs import ADDR_RE, parse_html, parse_llms, parse_sitemap
            mode = t.get("mode", "llms")
            if mode == "text":
                if len(text) < 200:
                    raise RuntimeError(f"只有 {len(text)} 字节，页面可能不对")
                addrs = len(set(ADDR_RE.findall(text)))
                return f"{len(text)} 字节 / {addrs} 个地址"
            if mode == "html":
                import urllib.parse
                parts = urllib.parse.urlsplit(t["url"])
                base = f"{parts.scheme}://{parts.netloc}"
                pages = parse_html(text, base, t.get("href_prefix", "/"))
            elif mode == "sitemap":
                pages = parse_sitemap(text)
            else:
                pages = parse_llms(text)
            if not pages:
                raise RuntimeError("解析到 0 个链接")
            return f"{len(pages)} 页"
        check(f"docs:{t.get('name')}", _docs)

    for r in (probes.get("github") or {}).get("repos", []):
        def _gh(r=r):
            branch = r.get("branch", "main")
            d = http.get_json(
                f"https://api.github.com/repos/{r['repo']}/git/trees/{branch}?recursive=1",
                headers={"Accept": "application/vnd.github+json"},
            )
            n = len([t for t in d.get("tree", []) if t.get("type") == "blob"])
            if not n:
                raise RuntimeError("空文件树")
            return f"{n} 个文件"
        check(f"github:{r['repo']}", _gh)

    from .coverage import chain_mode
    from .core.ws import WsError, validate_wss

    for chain, ccfg in ((probes.get("onchain") or {}).get("chains") or {}).items():
        def _chain(chain=chain, ccfg=ccfg):
            mode = chain_mode(ccfg)
            if mode != "configured":
                return f"{mode}：不连接、不用 HTTP 轮询代替"
            try:
                validate_wss(ccfg.get("wss") or "")
            except WsError as exc:
                raise RuntimeError(str(exc)) from exc
            return "WSS 地址格式通过。doctor 不发起订阅，避免误连节点"
        check(f"onchain:{chain}", _chain)

    print(f"\nradar {VERSION} 自检\n" + "-" * 60)
    ok_count = 0
    for ok, name, detail in results:
        print(f"{'✅' if ok else '❌'} {name:32} {detail}")
        ok_count += ok
    print("-" * 60)
    print(f"{ok_count}/{len(results)} 通过")
    return ok_count == len(results)


def tg_discover(http, token):
    """Print the chat_id(s) that have talked to the bot recently."""
    if not token:
        print("需要 token：--tg-token <TOKEN> 或环境变量 RADAR_TG_TOKEN")
        return 1
    base = f"https://api.telegram.org/bot{token}"
    try:
        me = http.get_json(f"{base}/getMe")
    except Exception as e:  # noqa: BLE001
        print(f"❌ token 无效或网络不通: {e}")
        return 1
    if not me.get("ok"):
        print(f"❌ getMe 失败: {me}")
        return 1
    bot = me["result"]
    print(f"✅ bot: @{bot.get('username')} ({bot.get('first_name')})")

    upd = http.get_json(f"{base}/getUpdates")
    chats = {}
    for item in upd.get("result", []):
        msg = item.get("message") or item.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            label = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            chats[chat["id"]] = f"{chat.get('type')} {label}".strip()
    if not chats:
        print("⚠️  还没有收到任何消息。先在 Telegram 里给这个 bot 发一句 /start，再跑一次。")
        return 2
    print("\n可用的 chat_id：")
    for cid, desc in chats.items():
        print(f"  {cid}   {desc}")
    print("\n填进 /etc/mode-radar.env：")
    print(f"  RADAR_TG_TOKEN={token}")
    print(f"  RADAR_TG_CHAT={list(chats)[0]}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - older interpreters / wrapped streams
            pass

    p = argparse.ArgumentParser(prog="radar", description="FLAP / four.meme 新模式雷达")
    p.add_argument("--config", default=os.path.join(HERE, "config.json"))
    p.add_argument("--db", default=os.path.join(os.path.dirname(HERE), "data", "radar.sqlite3"))
    p.add_argument("--once", action="store_true", help="跑一轮就退出")
    p.add_argument("--loop", action="store_true", help="常驻运行")
    p.add_argument("--doctor", action="store_true", help="部署前自检所有端点")
    p.add_argument("--probe", action="append", choices=sorted(PROBES), help="只跑指定探针")
    p.add_argument("--test-alert", action="store_true", help="发一条测试告警")
    p.add_argument("--events", type=int, default=0, help="打印最近 N 条告警")
    p.add_argument("--state", action="store_true", help="打印游标/基线")
    p.add_argument("--version", action="version", version=f"radar {VERSION}")
    p.add_argument("--tg-discover", action="store_true",
                   help="用 bot token 查 chat_id（先给 bot 发一条消息）")
    p.add_argument("--tg-token", default="", help="配合 --tg-discover 使用")
    p.add_argument("--export-html", default="", help="导出单文件网页到指定路径")
    p.add_argument("--export-json", default="", help="同时导出 JSON 快照")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    http, state, notifier, probes = build(cfg, args.db, only=args.probe)
    ctx = Ctx(cfg=cfg, http=http, state=state,
              log=lambda m: print(time.strftime("%m-%d %H:%M:%S"), m, flush=True))

    if args.tg_discover:
        return tg_discover(http, args.tg_token or os.environ.get("RADAR_TG_TOKEN", ""))

    if args.doctor:
        return 0 if doctor(cfg, http) else 1

    if args.test_alert:
        notifier.send([Signal(
            source="radar", key="test", kind="new", level="crit",
            title="测试告警：通道正常", detail=f"radar {VERSION} @ {socket_host()}",
        )])
        return 0

    if args.events:
        for row in state.recent_events(args.events):
            ts = time.strftime("%m-%d %H:%M", time.localtime(row["ts"]))
            print(f"{ts} [{row['level']:4}] {row['source']:34} {row['title']}")
            if row["detail"]:
                print(f"            {row['detail'][:200]}")
            if row["url"]:
                print(f"            {row['url']}")
        return 0

    if args.state:
        chains = (cfg.get("probes", {}).get("onchain", {}).get("chains") or {})
        for chain in chains:
            print(f"onchain:{chain} cursor = {state.get_meta('cursor:' + chain)}")
        for t in cfg.get("probes", {}).get("docs", {}).get("targets", []):
            print(f"docs:{t['name']} baseline = {bool(state.get_meta('docs_baseline:' + t['name']))}")
        for r in cfg.get("probes", {}).get("github", {}).get("repos", []):
            print(f"github:{r['repo']} baseline = {bool(state.get_meta('github_baseline:' + r['repo']))}")
        return 0

    if args.export_html or args.export_json:
        from .export import export
        data = export(cfg, state, args.export_html or None, args.export_json or None)
        o = data["overview"]
        if args.export_html:
            print(f"✅ 网页已导出: {args.export_html}")
        if args.export_json:
            print(f"✅ JSON 已导出: {args.export_json}")
        print(f"   告警 {o['events']} 条（高危 {o['crit']}），"
              f"合约 {o['contracts']}，文档 {o['docs']}，仓库 {o['repos']}，"
              f"模式编号 {len(data['registries'])} 个")
        return 0

    if not probes:
        print("没有启用的探针，检查 config.json")
        return 1

    if args.loop:
        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, lambda *_: _STOP.set())
            except (ValueError, OSError):
                pass
        from .bridge import Bridge
        bridge = None
        try:
            bridge = Bridge(cfg, state, os.environ)
            bridge.start()
            print(f"[bridge] 本机只读 http://{bridge.host}:{bridge.port}")
        except RuntimeError as exc:
            print(f"[bridge] 未启动（网站会显示未配置）：{exc}")
        print(f"radar {VERSION} 启动 | db={state.path}")
        for probe in probes:
            print(f"  - {probe.name:8} 每 {probe.interval}s")
        print("按 Ctrl+C 停止", flush=True)

        next_due = {p.name: 0 for p in probes}
        hb_hours = float((cfg.get("notify") or {}).get("heartbeat_hours") or 0)

        def heartbeat():
            """Silence must be distinguishable from death."""
            if hb_hours <= 0:
                return
            now = time.time()
            last = state.get_meta("heartbeat_ts")
            if last and now - int(last) < hb_hours * 3600:
                return
            state.set_meta("heartbeat_ts", int(now))
            n24 = state.count_events_since(now - 86400)
            cursor = state.get_meta("head:bsc") or "?"
            notifier.send([Signal(
                source="radar", key="heartbeat", kind="new", level="info",
                title=f"雷达在线 | 24h 告警 {n24} 条 | BSC 区块 {cursor} | "
                      f"待重试 {state.outbox_size()} 条",
                detail="这条心跳说明进程活着、时间表在转。收不到心跳 = 该看服务了。",
            )])

        while not _STOP.is_set():
            heartbeat()
            notifier.flush()
            for probe in probes:
                if _STOP.is_set():
                    break
                if time.time() >= next_due[probe.name]:
                    run_probe(probe, ctx, state, notifier)
                    next_due[probe.name] = time.time() + probe.interval
            _STOP.wait(5)
        for probe in probes:
            shutdown = getattr(probe, "shutdown", None)
            if shutdown:
                shutdown()
        if bridge is not None:
            bridge.stop()
        print("已停止", flush=True)
        return 0

    total = 0
    for probe in probes:
        total += run_probe(probe, ctx, state, notifier)
    print(f"完成：{total} 条新告警")
    return 0


def socket_host():
    import socket
    try:
        return socket.gethostname()
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
