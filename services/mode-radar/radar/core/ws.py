"""Minimal stdlib WebSocket client for eth_subscribe.

Chain monitoring is allowed only as a WSS subscription to newHeads and logs.
This module refuses HTTP RPC, cleartext ws://, and the local wallet/sniper port.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import urllib.parse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
FORBIDDEN_PORTS = {8545}
FORBIDDEN_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"}


class WsError(RuntimeError):
    pass


def validate_wss(url: str) -> urllib.parse.SplitResult:
    """Accept only wss:// endpoints that are not the sniper/wallet RPC."""
    if not isinstance(url, str) or not url.strip():
        raise WsError("未配置 WSS")
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme != "wss":
        raise WsError("链上监控只接受 wss:// 订阅，不使用 HTTP 轮询或 ws://")
    if parts.username or parts.password:
        raise WsError("WSS 地址不能把密钥写进 URL")
    host = (parts.hostname or "").lower()
    if not host:
        raise WsError("WSS 主机名为空")
    port = parts.port or 443
    if port in FORBIDDEN_PORTS and host in FORBIDDEN_HOSTS:
        raise WsError("拒绝连接本机 8545（钱包/sniper 专用 RPC）")
    if port in (4000, 443) and host in FORBIDDEN_HOSTS and port == 4000:
        raise WsError("拒绝把网站端口当作链节点")
    return parts


class WsRpc:
    """One WSS JSON-RPC connection. The caller owns the read loop."""

    def __init__(self, url: str, timeout: float = 25):
        self.parts = validate_wss(url)
        self.timeout = timeout
        self.sock: ssl.SSLSocket | None = None
        self._buf = b""

    def connect(self):
        host = self.parts.hostname or ""
        port = self.parts.port or 443
        raw = socket.create_connection((host, port), timeout=self.timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw, server_hostname=host)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = self.parts.path or "/"
        if self.parts.query:
            path += "?" + self.parts.query
        host_header = host if port == 443 else f"{host}:{port}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode())
        header = self._read_until(b"\r\n\r\n")
        status = header.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise WsError(f"WSS 握手失败: {status[:120]!r}")
        accept_ok = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest())
        if accept_ok not in header:
            raise WsError("WSS 握手校验失败")
        return self

    def close(self):
        sock = self.sock
        self.sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def send_text(self, text: str):
        self._send(1, text.encode())

    def send_json(self, payload: dict):
        self.send_text(json.dumps(payload, separators=(",", ":")))

    def read_message(self) -> str | None:
        """Return one text message. None means a clean close."""
        fragments: list[bytes] = []
        opcode = None
        while True:
            fin, op, payload = self._read_frame()
            if op == 8:
                self.close()
                return None
            if op == 9:
                self._send(10, payload)
                continue
            if op == 10:
                continue
            if op == 0 and opcode == 1:
                fragments.append(payload)
            elif op == 1:
                opcode = 1
                fragments = [payload]
            else:
                raise WsError(f"不支持的 WebSocket 帧 {op}")
            if fin:
                if opcode != 1:
                    raise WsError("WSS 收到非文本消息")
                return b"".join(fragments).decode("utf-8", "replace")

    def _send(self, opcode: int, payload: bytes):
        sock = self.sock
        if sock is None:
            raise WsError("WSS 未连接")
        mask = os.urandom(4)
        n = len(payload)
        header = bytes([0x80 | opcode])
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        sock.sendall(header + mask + masked)

    def _read_frame(self):
        head = self._read_exact(2)
        b0, b1 = head[0], head[1]
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > 8_000_000:
            raise WsError("WSS 帧过大")
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            sock = self.sock
            if sock is None:
                raise WsError("WSS 已关闭")
            try:
                chunk = sock.recv(max(4096, n - len(self._buf)))
            except socket.timeout as exc:
                raise WsError("WSS 读超时") from exc
            if not chunk:
                raise WsError("WSS 连接被关闭")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buf:
            sock = self.sock
            if sock is None:
                raise WsError("WSS 已关闭")
            chunk = sock.recv(4096)
            if not chunk:
                raise WsError("WSS 握手中断")
            self._buf += chunk
            if len(self._buf) > 65536:
                raise WsError("WSS 握手响应过大")
        idx = self._buf.index(marker) + len(marker)
        out, self._buf = self._buf[:idx], self._buf[idx:]
        return out
