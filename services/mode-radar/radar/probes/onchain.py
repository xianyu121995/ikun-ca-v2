"""On-chain probe: WSS subscriptions only.

newHeads drives identity reads. logs subscription drives enum values.
There is no eth_getLogs interval. With no wss:// endpoint the chain is
unconfigured and this probe does not open a socket.
"""

from __future__ import annotations

import json
import threading
import time

from ..core.sanitize import redact, safe_https
from ..core.ws import WsError, WsRpc, validate_wss
from ..coverage import chain_mode
from .base import Probe, Signal, decode_event, parse_signature, topic0

MAX_GAP_BLOCKS = 50_000
STALE_SECONDS = 90
LINK_HOSTS = {"bscscan.com", "testnet.bscscan.com"}


def _tx_url(ccfg, tx):
    if not isinstance(tx, str) or len(tx) != 66 or not tx.startswith("0x"):
        return ""
    try:
        int(tx[2:], 16)
    except ValueError:
        return ""
    explorer = ccfg.get("explorer") or {}
    tpl = explorer.get("tx") or ""
    if "{tx}" not in tpl:
        return ""
    return safe_https(tpl.format(tx=tx), LINK_HOSTS)


def _norm(value) -> str:
    return str(value).lower()


class OnchainProbe(Probe):
    name = "onchain"
    default_interval = 5

    def __init__(self, cfg, http, state):
        super().__init__(cfg, http, state)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._queue: dict[str, list] = {}
        self._threads: dict[str, threading.Thread] = {}

    def shutdown(self):
        self._stop.set()

    def run(self, ctx):
        signals = []
        for chain, ccfg in (self.cfg.get("chains") or {}).items():
            mode = chain_mode(ccfg)
            ctx.state.set_meta(f"chain_mode:{chain}", mode)
            if mode != "configured":
                ctx.state.set_meta(f"chain_link:{chain}", mode)
                detail = "未配置 WSS，链上路径已禁用" if mode == "unconfigured" else "该链在配置中关闭"
                ctx.state.set_meta(f"chain_detail:{chain}", detail)
                continue
            try:
                validate_wss(ccfg.get("wss") or "")
            except WsError as exc:
                ctx.state.set_meta(f"chain_link:{chain}", "unconfigured")
                ctx.state.set_meta(f"chain_detail:{chain}", redact(str(exc), 180))
                continue
            self._ensure(chain, ccfg, ctx)
            signals.extend(self._drain(chain))
        return signals

    # -------------------------------------------------------------- pure
    def seed_enums(self, ctx, chain, ccfg):
        """Record configured known values once. This is not a historical alert."""
        if ctx.state.get_meta(f"onchain_enum_baseline:{chain}"):
            return []
        source = f"onchain:{chain}"
        count = 0
        for event in ccfg.get("events") or []:
            for watch in event.get("watch") or []:
                label = watch.get("label") or "arg"
                for value in (watch.get("known") or {}):
                    vkey = f"{event.get('name')}:{label}={_norm(value)}"
                    ctx.state.observe(source, f"enum:{vkey}", _norm(value))
                    count += 1
        ctx.state.set_meta(f"onchain_enum_baseline:{chain}", 1)
        return [Signal(
            source=source, key="enum_baseline", kind="baseline", level="info",
            title=f"已建立 {chain} 事件取值基线（配置内 {count} 个已知取值）",
            detail="首次只记录已知取值，不把它们报成新变化。之后 WSS 上出现未见过的取值才告警。",
            fingerprint="enum-baseline",
        )]

    def note_head(self, ctx, chain, number: int):
        source = f"onchain:{chain}"
        prev = ctx.state.get_meta(f"head:{chain}")
        ctx.state.set_meta(f"head:{chain}", number)
        ctx.state.set_meta(f"head_ts:{chain}", int(time.time()))
        ctx.state.set_meta(f"chain_link:{chain}", "live")
        ctx.state.set_meta(f"chain_detail:{chain}", f"最近区块 {number}")
        if prev is None:
            return []
        gap = number - int(prev)
        if gap > MAX_GAP_BLOCKS:
            return [Signal(
                source=source, key="gap", kind="changed", level="warn",
                title=f"{chain} 订阅中断，区块跳过 {gap}",
                detail="断线期间没有用 HTTP 回补日志。这段里第一次出现的新取值可能没有被看到。",
                payload={"from": int(prev), "to": number, "gap": gap},
                fingerprint=f"gap:{prev}:{number}",
            )]
        return []

    def apply_log(self, ctx, chain, ccfg, log):
        """Classify one subscribed log. Baseline must already exist."""
        if not ctx.state.get_meta(f"onchain_enum_baseline:{chain}"):
            return []
        events = ccfg.get("events") or []
        by_topic = {topic0(e["signature"]).lower(): e for e in events if e.get("signature")}
        topics = [str(t).lower() for t in (log.get("topics") or [])]
        if not topics or topics[0] not in by_topic:
            return []
        event = by_topic[topics[0]]
        decoded = decode_event(event["signature"], {**log, "topics": topics}, int(event.get("indexed") or 0))
        if not decoded:
            return []
        arg_types = parse_signature(event["signature"])[1]
        source = f"onchain:{chain}"
        out = []
        seen = set()
        for watch in event.get("watch") or []:
            idx = int(watch.get("index", -1))
            if idx < 0 or idx >= len(arg_types):
                continue
            value = decoded.get(f"{idx}_{arg_types[idx]}")
            if value is None:
                continue
            label = watch.get("label") or f"arg{idx}"
            shown = _norm(value)
            vkey = f"{event['name']}:{label}={shown}"
            if vkey in seen:
                continue
            seen.add(vkey)
            state, _old = ctx.state.observe(source, f"enum:{vkey}", shown)
            if state != "new":
                continue
            known = {_norm(k): v for k, v in (watch.get("known") or {}).items()}
            known_name = known.get(shown, "")
            entity_idx = int(watch.get("entity_index", 0))
            entity = decoded.get(f"{entity_idx}_{arg_types[entity_idx]}") if entity_idx < len(arg_types) else ""
            tx = str(log.get("transactionHash") or "")
            out.append(Signal(
                source=source,
                key=f"enum:{vkey}",
                kind="new",
                level=watch.get("level") or "crit",
                title=f"{chain} {event['name']} 出现新取值 {label}={shown}"
                      + (f"（{known_name}）" if known_name else "（未登记）"),
                detail=redact(
                    f"合约 {log.get('address')} 实体={entity} tx={tx}",
                    400,
                ),
                url=_tx_url(ccfg, tx),
                payload={
                    "event": event["name"], "label": label, "value": shown,
                    "entity": str(entity), "tx": tx if tx.startswith("0x") else "",
                },
                fingerprint=f"{vkey}|{tx}",
            ))
        return out

    def apply_identity(self, ctx, chain, name, ident):
        source = f"onchain:{chain}"
        state, old = ctx.state.observe(source, f"identity:{name}", ident)
        if not ctx.state.get_meta(f"onchain_baseline:{chain}"):
            return []
        if state != "changed" or not old:
            return []
        diffs = {
            k: (old.get(k), ident.get(k))
            for k in set(old) | set(ident)
            if old.get(k) != ident.get(k)
        }
        return [Signal(
            source=source, key=f"identity:{name}", kind="changed", level="crit",
            title=f"{chain} {name} 合约实现变更",
            detail=redact(f"字段变化：{diffs}", 400),
            payload={"diffs": {k: [str(a), str(b)] for k, (a, b) in diffs.items()}},
            fingerprint=str(sorted((k, str(v)) for k, v in diffs.items())),
        )]

    def seal_identity(self, ctx, chain, names):
        if ctx.state.get_meta(f"onchain_baseline:{chain}"):
            return []
        ctx.state.set_meta(f"onchain_baseline:{chain}", 1)
        return [Signal(
            source=f"onchain:{chain}", key="baseline", kind="baseline", level="info",
            title=f"已登记 {chain} 的 {len(names)} 个监控合约",
            detail="、".join(names),
            fingerprint="identity-baseline",
        )]

    # -------------------------------------------------------------- socket
    def _ensure(self, chain, ccfg, ctx):
        with self._lock:
            thread = self._threads.get(chain)
            if thread and thread.is_alive():
                return
            thread = threading.Thread(
                target=self._serve, args=(chain, ccfg, ctx), name=f"radar-wss-{chain}", daemon=True,
            )
            self._threads[chain] = thread
            thread.start()

    def _drain(self, chain):
        with self._lock:
            items = self._queue.pop(chain, [])
        return items

    def _push(self, chain, signals):
        if not signals:
            return
        with self._lock:
            self._queue.setdefault(chain, []).extend(signals)

    def _serve(self, chain, ccfg, ctx):
        backoff = 1
        while not self._stop.is_set():
            try:
                self._session(chain, ccfg, ctx)
                backoff = 1
            except Exception as exc:  # noqa: BLE001 - one chain must not kill the process
                ctx.state.set_meta(f"chain_link:{chain}", "disconnected")
                ctx.state.set_meta(f"chain_detail:{chain}", redact(str(exc), 180) or "WSS 断开")
                ctx.log(f"[onchain] {chain} 订阅断开，{backoff}s 后重连")
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, 30)

    def _session(self, chain, ccfg, ctx):
        ws = WsRpc(ccfg["wss"], timeout=ccfg.get("timeout", 25))
        try:
            ws.connect()
            ctx.state.set_meta(f"chain_link:{chain}", "live")
            self._push(chain, self.seed_enums(ctx, chain, ccfg))
            def on_other(message, chain=chain, ccfg=ccfg, ctx=ctx):
                self._on_subscription(ctx, chain, ccfg, message, ws)

            chain_id = _rpc(ws, "eth_chainId", [], on_other)
            expected = ccfg.get("chain_id")
            if expected and int(chain_id, 16) != int(expected):
                raise WsError("chain_id 与配置不一致")
            _rpc(ws, "eth_subscribe", ["newHeads"], on_other)
            events = ccfg.get("events") or []
            addresses = ccfg.get("log_addresses") or []
            if events and addresses:
                topics = [topic0(e["signature"]) for e in events if e.get("signature")]
                _rpc(ws, "eth_subscribe", ["logs", {"address": addresses, "topics": [topics]}], on_other)
            last_data = time.time()
            quiet = 0
            while not self._stop.is_set():
                try:
                    raw = ws.read_message()
                except WsError as exc:
                    if "超时" in str(exc):
                        quiet += 1
                        age = time.time() - last_data
                        if age >= STALE_SECONDS:
                            ctx.state.set_meta(f"chain_link:{chain}", "stale")
                            ctx.state.set_meta(f"chain_detail:{chain}", "超过 90 秒没有新区块，数据滞后")
                        if quiet >= 4:
                            raise
                        continue
                    raise
                if raw is None:
                    raise WsError("WSS 对端关闭")
                quiet = 0
                last_data = time.time()
                self._on_text(ctx, chain, ccfg, raw, ws)
        finally:
            ws.close()

    def _on_text(self, ctx, chain, ccfg, raw, ws):
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._on_subscription(ctx, chain, ccfg, message, ws)

    def _on_subscription(self, ctx, chain, ccfg, message, ws):
        if message.get("method") != "eth_subscription":
            return
        result = (message.get("params") or {}).get("result") or {}
        if isinstance(result, dict) and result.get("topics"):
            self._push(chain, self.apply_log(ctx, chain, ccfg, result))
        elif isinstance(result, dict) and result.get("number"):
            number = int(result["number"], 16)
            self._push(chain, self.note_head(ctx, chain, number))
            self._maybe_identity(ws, ctx, chain, ccfg)

    def _maybe_identity(self, ws, ctx, chain, ccfg):
        interval = int(ccfg.get("identity_interval", 600))
        last = ctx.state.get_meta(f"identity_ts:{chain}")
        if last and time.time() - int(last) < interval:
            return
        ctx.state.set_meta(f"identity_ts:{chain}", int(time.time()))
        names = []
        for contract in ccfg.get("contracts") or []:
            name = contract.get("name") or contract.get("address")
            try:
                ident = _identity(ws, contract.get("address"), contract.get("kind", "auto"),
                              lambda message: self._on_subscription(ctx, chain, ccfg, message, ws))
            except (WsError, ValueError, TypeError):
                continue
            names.append(name)
            self._push(chain, self.apply_identity(ctx, chain, name, ident))
        if names:
            self._push(chain, self.seal_identity(ctx, chain, names))


def _rpc(ws: WsRpc, method: str, params, on_other=None):
    rid = f"{method}:{time.time_ns()}"
    ws.send_json({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    deadline = time.time() + ws.timeout
    while time.time() < deadline:
        raw = ws.read_message()
        if raw is None:
            raise WsError("WSS 在请求中关闭")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if message.get("id") != rid:
            if on_other and message.get("method") == "eth_subscription":
                on_other(message)
            continue
        if message.get("error"):
            raise WsError("节点拒绝请求")
        return message.get("result")
    raise WsError("WSS 请求超时")


def _identity(ws: WsRpc, address, kind, on_other=None):
    from ..core.keccak import keccak_hex
    from ..core.rpc import EIP1967_ADMIN_SLOT, EIP1967_BEACON_SLOT, EIP1967_IMPL_SLOT, ZERO_ADDR, to_addr

    code = _rpc(ws, "eth_getCode", [address, "latest"], on_other) or "0x"
    ident = {
        "address": address.lower(),
        "code": keccak_hex(bytes.fromhex(code[2:])) if len(code) > 2 else "empty",
    }
    if kind in ("proxy", "auto"):
        impl = to_addr(_rpc(ws, "eth_getStorageAt", [address, EIP1967_IMPL_SLOT, "latest"], on_other))
        admin = to_addr(_rpc(ws, "eth_getStorageAt", [address, EIP1967_ADMIN_SLOT, "latest"], on_other))
        beacon = to_addr(_rpc(ws, "eth_getStorageAt", [address, EIP1967_BEACON_SLOT, "latest"], on_other))
        if impl != ZERO_ADDR or admin != ZERO_ADDR or beacon != ZERO_ADDR:
            ident.update({"impl": impl, "admin": admin, "beacon": beacon})
    return ident
