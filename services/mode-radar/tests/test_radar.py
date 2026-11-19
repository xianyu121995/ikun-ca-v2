import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from radar.core.keccak import event_topic0, keccak_hex  # noqa: E402
from radar.core.state import State  # noqa: E402
from radar.probes import onchain as onchain_mod  # noqa: E402
from radar.probes.base import Ctx, Signal, decode_event, parse_signature  # noqa: E402
from radar.probes.docs import DocsProbe  # noqa: E402

TMP_ROOT = os.path.join(ROOT, ".tmp")
os.makedirs(TMP_ROOT, exist_ok=True)


def _tmpdir():
    """Workspace-local scratch dir.

    tempfile.mkdtemp() applies mode 0700, whose Windows ACL does not inherit the
    workspace grant, so the sandboxed process cannot write inside it.
    """
    path = os.path.join(TMP_ROOT, "t" + uuid.uuid4().hex[:12])
    os.makedirs(path, exist_ok=True)
    return path


class TestKeccak(unittest.TestCase):
    def test_vectors(self):
        self.assertEqual(
            keccak_hex(b""),
            "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
        )
        self.assertEqual(
            event_topic0("Transfer(address,address,uint256)"),
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        )

    def test_signature_parse(self):
        name, types = parse_signature("TokenExtensionEnabled(address,bytes32,address,uint8)")
        self.assertEqual(name, "TokenExtensionEnabled")
        self.assertEqual(types, ["address", "bytes32", "address", "uint8"])


class TestDecode(unittest.TestCase):
    def test_extension_event(self):
        sig = "TokenExtensionEnabled(address,bytes32,address,uint8)"
        token = "00" * 12 + "aa" * 20
        ext = "9c312f81d9a1b68ba5472ca93c5447d57f897fbf4a8c468b315a67fe8016d1ab"
        eaddr = "00" * 12 + "bb" * 20
        version = "0" * 63 + "1"
        log = {"topics": [event_topic0(sig)], "data": "0x" + token + ext + eaddr + version}
        got = decode_event(sig, log, 0)
        self.assertEqual(got["0_address"], "0x" + "aa" * 20)
        self.assertEqual(got["1_bytes32"], "0x" + ext)
        self.assertEqual(got["3_uint8"], 1)


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802
        body = self.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class TestDocsProbe(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        self.tmp = _tmpdir()
        _Handler.routes = {}

    def tearDown(self):
        self.server.shutdown()

    def _run(self, text, **target_extra):
        _Handler.routes["/llms.txt"] = text
        from radar.core.http import Http
        from radar.core.state import State

        target = {
            "name": "t", "mode": "llms",
            "url": f"http://127.0.0.1:{self.port}/llms.txt",
            "hot": ["mode"], "warm": ["guide"], "ignore": [],
        }
        target.update(target_extra)
        cfg = {"enabled": True, "interval": 10, "targets": [target]}
        state = State(os.path.join(self.tmp, "t.sqlite3"))
        probe = DocsProbe(cfg, Http(retries=1, timeout=5), state)
        ctx = Ctx(cfg=cfg, http=probe.http, state=state, log=lambda *a: None)
        return probe.run(ctx), state

    def test_baseline_then_new_page(self):
        base = "- [Home](https://x.test/home.md)\n- [Guide](https://x.test/guide.md)\n"
        sigs, state = self._run(base)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0].kind, "baseline")
        self.assertIn("基线", sigs[0].title)

        sigs2, state = self._run(base + "- [Some New Mode](https://x.test/new-mode.md)\n")
        self.assertEqual(len(sigs2), 1)
        self.assertEqual(sigs2[0].level, "crit")
        self.assertEqual(sigs2[0].key, "https://x.test/new-mode.md")

    def test_no_change_no_signal(self):
        base = "- [Home](https://x.test/home.md)\n"
        self._run(base)
        sigs, _ = self._run(base)
        self.assertEqual(sigs, [])

    def test_content_change_without_new_page(self):
        """A new section inside an existing page must not be invisible."""
        base = "- [Home](https://x.test/home.md)\n"
        self._run(base)
        sigs, _ = self._run(base + "\n新增：Agent ID gate 模式\n")
        self.assertTrue(any(s.key == "__content__" and s.level == "warn" for s in sigs))

    def test_new_contract_address(self):
        base = "- [A](https://x.test/a.md)\nTokenManager 0x" + "aa" * 20 + "\n"
        self._run(base, watch_addresses=True)
        sigs, _ = self._run(base + "NewPortal 0x" + "bb" * 20 + "\n", watch_addresses=True)
        crit = [s for s in sigs if s.key.startswith("addr:")]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0].level, "crit")
        self.assertIn("0x" + "bb" * 20, crit[0].title)

    def test_deleted_page_after_baseline(self):
        base = "- [Home](https://x.test/home.md)\n- [Guide](https://x.test/guide.md)\n"
        self._run(base)
        sigs, _state = self._run("- [Home](https://x.test/home.md)\n")
        gone = [s for s in sigs if s.kind == "gone"]
        self.assertEqual(len(gone), 1)
        self.assertIn("guide.md", gone[0].title)
        self.assertEqual(gone[0].url, "")


class TestOutbox(unittest.TestCase):
    """A failed push must not lose the alert."""

    def test_requeue_then_flush(self):
        from types import SimpleNamespace

        from radar.core.notify import Notifier

        tmp = _tmpdir()
        st = State(os.path.join(tmp, "o.sqlite3"))
        cfg = {"console": False, "min_level": "info", "allow_external": True,
               "webhook_url": "https://example.test/hook"}

        class _Fail:
            def post_json(self, *a, **k):
                raise RuntimeError("boom")

        class _Ok:
            def post_json(self, *a, **k):
                return {}

        sig = Signal(source="s", key="k", kind="new", level="crit", title="新模式")
        n = Notifier(cfg, _Fail(), st)
        self.assertFalse(n.send([sig]))
        self.assertEqual(st.outbox_size(), 1)

        n2 = Notifier(cfg, _Ok(), st)
        self.assertEqual(n2.flush(), 1)
        self.assertEqual(st.outbox_size(), 0)

        # SimpleNamespace round-trip is what flush relies on
        self.assertEqual(SimpleNamespace(**sig.__dict__).title, "新模式")


class TestState(unittest.TestCase):
    def test_dedupe(self):
        tmp = _tmpdir()
        st = State(os.path.join(tmp, "s.sqlite3"))
        sig = Signal(source="s", key="k", kind="new", level="crit", title="t")
        self.assertIsNotNone(st.emit(sig))
        self.assertIsNone(st.emit(sig))

    def test_observe_transitions(self):
        tmp = _tmpdir()
        st = State(os.path.join(tmp, "s.sqlite3"))
        self.assertEqual(st.observe("a", "b", 1)[0], "new")
        self.assertEqual(st.observe("a", "b", 1)[0], "same")
        self.assertEqual(st.observe("a", "b", 2)[0], "changed")


class TestOnchainProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()

    def _log(self, value_hex, tx="11"):
        sig = "TokenExtensionEnabled(address,bytes32,address,uint8)"
        token = "00" * 12 + "cc" * 20
        return {
            "topics": [event_topic0(sig)],
            "data": "0x" + token + value_hex + ("00" * 12 + "bb" * 20) + ("0" * 63 + "1"),
            "address": "0xportal",
            "transactionHash": "0x" + tx * 32,
            "blockNumber": "0x3e8",
        }

    def _chain(self, **extra):
        chain = {
            "enabled": True,
            "wss": "",
            "log_addresses": ["0xportal"],
            "identity_interval": 0,
            "contracts": [{"name": "portal", "address": "0xabc", "kind": "proxy"}],
            "explorer": {"tx": "https://bscscan.com/tx/{tx}"},
            "events": [{
                "name": "TokenExtensionEnabled",
                "signature": "TokenExtensionEnabled(address,bytes32,address,uint8)",
                "indexed": 0,
                "watch": [{
                    "index": 1, "label": "extensionID", "entity_index": 0,
                    "level": "crit",
                    "known": {"0x" + "9c" * 32: "Agent ID gate v1"},
                }],
            }],
        }
        chain.update(extra)
        return chain

    def _probe(self, chain):
        from radar.core.http import Http
        cfg = {"enabled": True, "chains": {"bsc": chain}}
        state = State(os.path.join(self.tmp, "o.sqlite3"))
        probe = onchain_mod.OnchainProbe(cfg, Http(retries=1, timeout=5), state)
        ctx = Ctx(cfg=cfg, http=probe.http, state=state, log=lambda *a: None)
        return probe, ctx

    def test_missing_wss_does_not_poll(self):
        import socket
        probe, ctx = self._probe(self._chain())
        def boom(*_a, **_k):
            raise AssertionError("未配置 WSS 时不应打开套接字")
        orig = socket.create_connection
        socket.create_connection = boom
        try:
            signals = probe.run(ctx)
        finally:
            socket.create_connection = orig
        self.assertEqual(signals, [])
        self.assertEqual(ctx.state.get_meta("chain_link:bsc"), "unconfigured")
        self.assertNotIn("get_logs(", open(onchain_mod.__file__, encoding="utf-8").read())

    def test_http_and_sniper_rpc_rejected(self):
        from radar.core.ws import WsError, validate_wss
        for url in ("https://bsc-rpc.publicnode.com", "http://127.0.0.1:8545", "wss://127.0.0.1:8545", "ws://example.invalid/ws"):
            with self.assertRaises(WsError):
                validate_wss(url)
        self.assertEqual(validate_wss("wss://example.invalid/bsc").scheme, "wss")

    def test_known_value_silent_new_value_alert_and_reconnect_dedupe(self):
        known = "9c" * 32
        probe, ctx = self._probe(self._chain(wss="wss://example.invalid/ws"))
        first = probe.seed_enums(ctx, "bsc", probe.cfg["chains"]["bsc"])
        self.assertTrue(any("基线" in s.title for s in first))
        self.assertFalse(any(s.level == "crit" for s in first))
        chain = probe.cfg["chains"]["bsc"]
        self.assertEqual(probe.apply_log(ctx, "bsc", chain, self._log(known)), [])
        crit = probe.apply_log(ctx, "bsc", chain, self._log("77" * 32))
        self.assertEqual(len(crit), 1)
        self.assertIn("未登记", crit[0].title)
        self.assertTrue(crit[0].url.startswith("https://bscscan.com/tx/"))
        again = probe.apply_log(ctx, "bsc", chain, self._log("77" * 32))
        self.assertEqual(again, [])
        self.assertIsNotNone(ctx.state.emit(crit[0]))
        self.assertIsNone(ctx.state.emit(crit[0]))

    def test_contract_upgrade_after_baseline(self):
        probe, ctx = self._probe(self._chain())
        self.assertEqual(probe.apply_identity(ctx, "bsc", "portal", {"impl": "0x1", "code": "a"}), [])
        sealed = probe.seal_identity(ctx, "bsc", ["portal"])
        self.assertEqual(sealed[0].kind, "baseline")
        changed = probe.apply_identity(ctx, "bsc", "portal", {"impl": "0x2", "code": "a"})
        self.assertEqual(changed[0].level, "crit")
        self.assertEqual(probe.apply_identity(ctx, "bsc", "portal", {"impl": "0x2", "code": "a"}), [])

    def test_gap_without_backfill(self):
        probe, ctx = self._probe(self._chain())
        self.assertEqual(probe.note_head(ctx, "bsc", 10), [])
        gap = probe.note_head(ctx, "bsc", 10 + 50_001)
        self.assertEqual(gap[0].level, "warn")
        self.assertIn("没有用 HTTP 回补", gap[0].detail)

    def test_unsafe_log_url_dropped(self):
        probe, ctx = self._probe(self._chain(explorer={"tx": "javascript:alert({tx})"}))
        probe.seed_enums(ctx, "bsc", probe.cfg["chains"]["bsc"])
        crit = probe.apply_log(ctx, "bsc", probe.cfg["chains"]["bsc"], self._log("77" * 32, tx="22"))
        self.assertEqual(crit[0].url, "")


class _FakeHttp:
    """Duck-typed stand-in for radar.core.http.Http."""

    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, **kw):
        return self.payload


class TestGithubProbe(unittest.TestCase):
    def setUp(self):
        from radar.probes.github import GithubProbe

        self.GithubProbe = GithubProbe
        self.tmp = _tmpdir()
        self.state = State(os.path.join(self.tmp, "g.sqlite3"))
        self.cfg = {"enabled": True, "repos": [{"repo": "o/r", "branch": "main"}]}

    def _run(self, paths):
        tree = {"tree": [{"path": p, "type": "blob", "sha": "s" + p} for p in paths]}
        http = _FakeHttp(tree)
        probe = self.GithubProbe(self.cfg, http, self.state)
        ctx = Ctx(cfg=self.cfg, http=http, state=self.state, log=lambda *a: None)
        return probe.run(ctx)

    def test_new_contract_file_is_crit(self):
        base = ["README.md", "contracts/token/TaxToken.sol"]
        first = self._run(base)
        self.assertTrue(any("基线" in s.title for s in first))

        sigs = self._run(base + ["contracts/token/NewModeToken.sol"])
        crit = [s for s in sigs if s.level == "crit"]
        self.assertEqual(len(crit), 1)
        self.assertIn("NewModeToken.sol", crit[0].title)

        # unrelated new file stays low severity
        sigs2 = self._run(base + ["contracts/token/NewModeToken.sol", "assets/logo.png"])
        self.assertTrue(any(s.level == "info" for s in sigs2 if "logo" in s.key))

    def test_deleted_file(self):
        self._run(["README.md", "contracts/token/TaxToken.sol"])
        sigs = self._run(["README.md"])
        gone = [s for s in sigs if s.kind == "gone"]
        self.assertEqual(len(gone), 1)
        self.assertIn("TaxToken.sol", gone[0].title)


class TestExport(unittest.TestCase):
    def test_html_renders_and_escapes(self):
        from radar.export import collect, render_html

        tmp = _tmpdir()
        st = State(os.path.join(tmp, "e.sqlite3"))
        st.emit(Signal(source="onchain:bsc", key="k", kind="new", level="crit",
                       title="新模式 <X>", detail="d&d", url="https://e.test/t"))
        data = collect({"probes": {}}, st)
        page = render_html(data)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("新模式 &lt;X&gt;", page)   # escaped
        self.assertIn("高危", page)
        self.assertNotIn("{{", page)
        self.assertEqual(data["overview"]["crit"], 1)


class TestCoverageAndBridge(unittest.TestCase):
    def test_fourmeme_events_are_not_claimed(self):
        from radar.coverage import coverage_report
        cfg = json.load(open(os.path.join(ROOT, "radar", "config.json"), encoding="utf-8"))
        rows = {item["id"]: item for item in coverage_report(cfg)}
        self.assertEqual(rows["four-events"]["state"], "unconfigured")
        self.assertEqual(rows["four-docs"]["state"], "configured")
        self.assertEqual(rows["four-github"]["state"], "configured")
        self.assertEqual(rows["flap-github"]["state"], "configured")
        self.assertIn("flap-sh", rows["flap-github"]["summary"])
        self.assertIn("官方 owner 未配置", rows["four-github"]["limit"])
        self.assertIn("four-meme-community", rows["four-github"]["limit"])
        self.assertEqual(rows["flap-events"]["state"], "unconfigured")
        self.assertIn("不能宣称", rows["four-events"]["limit"])
        blob = json.dumps(cfg)
        self.assertNotIn("bsc-dataseed", blob)
        self.assertNotIn("publicnode", blob)
        self.assertNotIn("8545", blob)
        self.assertNotIn("twitterapi.io", blob)

    def test_bridge_hides_history_dedupes_reconnect_and_redacts(self):
        import http.client
        import socket
        from radar.bridge import Bridge

        tmp = _tmpdir()
        st = State(os.path.join(tmp, "b.sqlite3"))
        st.emit(Signal(source="docs:flap", key="old", kind="new", level="info",
                       title="历史事件不应推送", detail="bot123456:ABCDEFGHIJK wss://rpc.example/secret"))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        token = "t" * 40
        env = {"RADAR_BRIDGE_HOST": "127.0.0.1", "RADAR_BRIDGE_PORT": str(port), "RADAR_BRIDGE_TOKEN": token}
        cfg = json.load(open(os.path.join(ROOT, "radar", "config.json"), encoding="utf-8"))
        cfg["probes"]["onchain"]["chains"]["bsc"]["wss"] = "wss://secret.example/key"
        bridge = Bridge(cfg, st, env)
        bridge.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/v1/snapshot")
            self.assertEqual(conn.getresponse().status, 401)
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/v1/snapshot", headers={"Authorization": "Bearer " + token})
            body = conn.getresponse().read().decode()
            self.assertNotIn("secret.example", body)
            self.assertNotIn("ABCDEFGHIJK", body)
            self.assertNotIn(token, body)
            self.assertIn("未登记", body) if False else self.assertIn("four-events", body)
            self.assertIn("[已隐藏]", body)

            held = {}

            def read_first():
                client = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                client.request("GET", "/v1/events", headers={"Authorization": "Bearer " + token})
                response = client.getresponse()
                chunk = response.fp.read(240)
                held["first"] = chunk.decode()
                client.close()

            # Fresh clients must not be handed the historical row.
            read_first()
            self.assertIn("hello", held["first"])
            self.assertNotIn("历史事件不应推送", held["first"])

            st.emit(Signal(source="docs:flap", key="new", kind="new", level="crit", title="新变化应推送", detail="ok"))
            latest = st.max_event_id()
            client = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            client.request("GET", "/v1/events", headers={
                "Authorization": "Bearer " + token,
                "Last-Event-ID": str(latest - 1),
            })
            text = client.getresponse().read(800).decode()
            client.close()
            self.assertEqual(text.count("新变化应推送"), 1)
            self.assertNotIn("历史事件不应推送", text)
        finally:
            bridge.stop()


class TestWsFrames(unittest.TestCase):
    def test_roundtrip_over_local_tls(self):
        import shutil
        import socket
        import ssl
        import subprocess
        import tempfile
        if shutil.which("openssl") is None:
            self.skipTest("openssl missing")
        from radar.core.ws import WsRpc
        tmp = tempfile.mkdtemp(prefix="radar-tls-")
        cert, key = os.path.join(tmp, "cert.pem"), os.path.join(tmp, "key.pem")
        subprocess.check_call(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key,
                               "-out", cert, "-days", "1", "-nodes", "-subj", "/CN=127.0.0.1",
                               "-addext", "subjectAltName=IP:127.0.0.1"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        raw = socket.socket()
        raw.bind(("127.0.0.1", 0))
        port = raw.getsockname()[1]
        raw.listen(1)
        raw.settimeout(5)
        holder = {}

        def serve():
            client, _addr = raw.accept()
            tls = ctx.wrap_socket(client, server_side=True)
            data = b""
            while b"\r\n\r\n" not in data:
                data += tls.recv(4096)
            key_line = [line for line in data.decode().split("\r\n") if line.lower().startswith("sec-websocket-key:")][0]
            wskey = key_line.split(":", 1)[1].strip()
            accept = base64_sha1(wskey)
            tls.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            frame = b""
            while len(frame) < 6:
                frame += tls.recv(64)
            # masked client text; just echo a server text frame
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "0xabc"}).encode()
            tls.sendall(bytes([0x81, len(payload)]) + payload)
            holder["ok"] = True
            tls.close()

        threading.Thread(target=serve, daemon=True).start()
        # The production client verifies certificates. This test installs the cert we just made.
        os.environ["SSL_CERT_FILE"] = cert
        try:
            rpc = WsRpc(f"wss://127.0.0.1:{port}/ws", timeout=5)
            rpc.connect()
            rpc.send_json({"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": ["newHeads"]})
            message = json.loads(rpc.read_message())
            self.assertEqual(message["result"], "0xabc")
            rpc.close()
        finally:
            os.environ.pop("SSL_CERT_FILE", None)
            raw.close()
        self.assertTrue(holder.get("ok"))
        self.assertNotEqual(port, 8545)


def base64_sha1(wskey):
    import base64
    import hashlib
    from radar.core.ws import GUID
    return base64.b64encode(hashlib.sha1((wskey + GUID).encode()).digest()).decode()


if __name__ == "__main__":
    unittest.main(verbosity=2)


