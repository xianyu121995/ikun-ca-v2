"""Shared types and ABI helpers for probes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.keccak import event_topic0

LEVELS = {"info": 0, "warn": 1, "crit": 2}

_SIG_RE = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*$")


@dataclass
class Signal:
    """One thing worth telling the user about."""

    source: str
    key: str
    kind: str  # new | changed | gone
    level: str  # info | warn | crit
    title: str
    detail: str = ""
    url: str = ""
    payload: dict = field(default_factory=dict)
    fingerprint: str | None = None  # extra entropy for dedupe


@dataclass
class Ctx:
    cfg: dict
    http: object
    state: object
    log: callable = print


def parse_signature(signature: str):
    """'TokenCreated(uint256,address,string)' -> ('TokenCreated', ['uint256','address','string'])."""
    m = _SIG_RE.match(signature.replace(" ", ""))
    if not m:
        raise ValueError(f"bad event signature: {signature}")
    name, raw = m.group(1), m.group(2)
    types = [t for t in raw.split(",") if t]
    return name, types


def topic0(signature: str) -> str:
    return event_topic0(signature)


def is_dynamic(typ: str) -> bool:
    return typ in ("string", "bytes") or typ.endswith("[]") or "[" in typ


def _decode_one(typ: str, word: str):
    v = int(word, 16)
    if typ == "address":
        return "0x" + word[-40:].lower()
    if typ == "bool":
        return bool(v)
    if typ == "bytes32":
        return "0x" + word
    if typ.startswith("bytes"):
        return "0x" + word
    if typ.startswith("uint"):
        return v
    if typ.startswith("int"):
        bits = int(typ[3:] or 256)
        return v - (1 << 256) if v >= (1 << (bits - 1)) else v
    return v


def decode_event(signature: str, log: dict, indexed: int = 0) -> dict:
    """Decode a log into {field: value}. Only static types are supported.

    `indexed` = how many leading params are indexed (they arrive as topics).
    Returns {} when the signature contains dynamic types.
    """
    _, types = parse_signature(signature)
    if any(is_dynamic(t) for t in types):
        return {}

    topics = log.get("topics") or []
    data = log.get("data") or "0x"
    body = data[2:] if data.startswith("0x") else data
    words = [body[i:i + 64] for i in range(0, len(body), 64)]

    out = {}
    pos = 0
    for i, typ in enumerate(types):
        if i < indexed:
            if i + 1 >= len(topics):
                return {}
            raw = topics[i + 1][2:].rjust(64, "0")
        else:
            if pos >= len(words):
                return {}
            raw = words[pos].rjust(64, "0")
            pos += 1
        out[f"{i}_{typ}"] = _decode_one(typ, raw)
    return out


def decode_named(signature: str, log: dict, indexed: int = 0) -> dict:
    """Like decode_event but keys are 'arg0', 'arg1'... paired with the type list."""
    _, types = parse_signature(signature)
    raw = decode_event(signature, log, indexed)
    out = {}
    for i, typ in enumerate(types):
        k = f"{i}_{typ}"
        if k not in raw:
            continue
        out[f"arg{i}"] = raw[k]
        out[f"arg{i}:type"] = typ
    return out


class Probe:
    name = "probe"
    default_interval = 300

    def __init__(self, cfg, http, state):
        self.cfg = cfg or {}
        self.http = http
        self.state = state
        self.interval = self.cfg.get("interval", self.default_interval)
        self.enabled = self.cfg.get("enabled", True)

    def run(self, ctx: Ctx):
        raise NotImplementedError
