"""Minimal JSON-RPC client for BSC-compatible nodes."""

from __future__ import annotations

import itertools

from .keccak import keccak_hex

EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
ZERO_ADDR = "0x" + "0" * 40


class RpcError(RuntimeError):
    pass


def to_addr(word: str) -> str:
    if not word or word in ("0x", "0x0"):
        return ZERO_ADDR
    w = word[2:] if word.startswith("0x") else word
    return "0x" + w[-40:].rjust(40, "0").lower()


class Rpc:
    def __init__(self, url, http, timeout=25):
        # `url` may be a single endpoint or a failover list
        self.urls = [url] if isinstance(url, str) else list(url)
        self.http = http
        self.timeout = timeout
        self._ids = itertools.count(1)
        self.idx = 0

    @property
    def url(self):
        return self.urls[self.idx]

    def _call(self, method, params):
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        last = RpcError(f"{method}: no endpoint configured")
        for attempt in range(len(self.urls)):
            i = (self.idx + attempt) % len(self.urls)
            try:
                res = self.http.post_json(self.urls[i], payload, timeout=self.timeout)
            except Exception as e:  # noqa: BLE001 - transport failure, try the next endpoint
                last = RpcError(f"{method}: {type(e).__name__}: {e}")
                continue
            if isinstance(res, dict) and res.get("error"):
                last = RpcError(f"{method}: {res['error']}")
                continue
            if not isinstance(res, dict) or "result" not in res:
                last = RpcError(f"{method}: unexpected response {str(res)[:200]}")
                continue
            self.idx = i
            return res["result"]
        raise last

    # ------------------------------------------------------------ chain
    def block_number(self) -> int:
        return int(self._call("eth_blockNumber", []), 16)

    def chain_id(self) -> int:
        return int(self._call("eth_chainId", []), 16)

    def get_code(self, address) -> str:
        return self._call("eth_getCode", [address, "latest"])

    def get_storage_at(self, address, slot) -> str:
        return self._call("eth_getStorageAt", [address, slot, "latest"])

    def eth_call(self, to, data) -> str:
        return self._call("eth_call", [{"to": to, "data": data}, "latest"])

    def get_logs(self, addresses, topics, from_block, to_block, max_range=2000, sleep=0.15):
        """Disabled. Live logs must come from a WSS eth_subscribe, not eth_getLogs polling."""
        raise RpcError("eth_getLogs 轮询已禁用；链上日志只能走 WSS eth_subscribe logs")

    # ------------------------------------------------------- contract id
    def contract_identity(self, address, kind="auto"):
        """A fingerprint that changes when a proxy is upgraded or the code is swapped."""
        ident = {"address": address.lower()}
        code = self.get_code(address)
        ident["code"] = keccak_hex(bytes.fromhex(code[2:])) if len(code) > 2 else "empty"
        if kind in ("proxy", "auto"):
            impl = to_addr(self.get_storage_at(address, EIP1967_IMPL_SLOT))
            admin = to_addr(self.get_storage_at(address, EIP1967_ADMIN_SLOT))
            beacon = to_addr(self.get_storage_at(address, EIP1967_BEACON_SLOT))
            if impl != ZERO_ADDR or admin != ZERO_ADDR or beacon != ZERO_ADDR:
                ident.update({"impl": impl, "admin": admin, "beacon": beacon})
        return ident
