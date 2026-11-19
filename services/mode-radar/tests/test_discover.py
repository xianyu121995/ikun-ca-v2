import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from radar.core.state import State  # noqa: E402
from radar.probes.base import Ctx  # noqa: E402
from radar.probes.discover import (  # noqa: E402
    DiscoverProbe,
    parse_any_github_repo,
    parse_github_links,
)

TMP = os.path.join(ROOT, ".tmp")
os.makedirs(TMP, exist_ok=True)


def _db():
    import uuid
    path = os.path.join(TMP, "d" + uuid.uuid4().hex[:8] + ".sqlite3")
    return State(path)


class FakeHttp:
    def __init__(self, pages=None, docs=None, fail_page=None):
        self.pages = pages or {}
        self.docs = docs or {}
        self.fail_page = fail_page
        self.calls = []

    def conditional_get(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        if "page=2" in url and self.fail_page == 2:
            return 500, {"x-ratelimit-remaining": "40"}, b""
        if "page=1" in url and self.fail_page == "rate":
            return 403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"}, b"rate"
        from urllib.parse import parse_qs, urlsplit
        page = parse_qs(urlsplit(url).query).get("page", ["1"])[0]
        body = json.dumps(self.pages.get(page, [])).encode()
        etag = '"p' + page + "-" + str(len(body)) + '"'
        if page == "1" and headers and headers.get("If-None-Match") == etag:
            return 304, {"etag": etag, "x-ratelimit-remaining": "40"}, b""
        return 200, {"etag": etag, "x-ratelimit-remaining": "40"}, body

    def get_text(self, url, **_kw):
        if url not in self.docs:
            raise RuntimeError("doc down")
        return self.docs[url]


def _repo(full, fork=False):
    return {"full_name": full, "fork": fork, "private": False}


class TestDiscover(unittest.TestCase):
    def _probe(self, http, **cfg):
        base = {
            "enabled": True,
            "owners": [{
                "login": "flap-sh",
                "project": "FLAP",
                "enabled": True,
                "evidence": ["https://docs.flap.sh/en/flap/developers/vault-developers/quick-start-vault-developers"],
            }],
            "doc_clues": [],
        }
        base.update(cfg)
        state = _db()
        probe = DiscoverProbe(base, http, state)
        ctx = Ctx(cfg=base, http=http, state=state, log=lambda *_a: None)
        return probe, ctx

    def test_links_stay_inside_verified_owner(self):
        text = """
        https://docs.flap.sh says https://github.com/flap-sh/FlapVaultExample/blob/main/README.md
        and https://github.com/four-meme-community/openfour-docs
        javascript:alert(1) https://user:pass@github.com/flap-sh/secret
        https://github.com.evil/flap-sh/nope
        https://github.com/flap-sh/../elsewhere
        """
        self.assertEqual(parse_github_links(text, ["flap-sh"]), {"flap-sh": {"FlapVaultExample"}})
        self.assertIn("four-meme-community/openfour-docs", parse_any_github_repo(text))
        self.assertNotIn("flap-sh/..", parse_any_github_repo(text))

    def test_baseline_then_new_repo_then_restart_dedupe(self):
        http = FakeHttp(pages={"1": [_repo("flap-sh/FlapVaultExample"), _repo("four-meme-community/openfour-docs"), _repo("flap-sh/forked", fork=True)]})
        probe, ctx = self._probe(http)
        first = probe.run(ctx)
        self.assertTrue(any(s.kind == "baseline" for s in first))
        self.assertFalse(any(s.level == "crit" for s in first))
        http.pages["1"].append(_repo("flap-sh/NewMode"))
        second = probe.run(ctx)
        crit = [s for s in second if s.level == "crit"]
        self.assertEqual(len(crit), 1)
        self.assertIn("FLAP", crit[0].title)
        self.assertIn("NewMode", crit[0].title)
        self.assertIn("docs.flap.sh", crit[0].detail)
        self.assertEqual(crit[0].url, "https://github.com/flap-sh/NewMode")
        again = probe.run(ctx)
        self.assertFalse(any(s.level == "crit" for s in again))
        restarted = DiscoverProbe(probe.cfg, http, ctx.state)
        ctx2 = Ctx(cfg=probe.cfg, http=http, state=ctx.state, log=lambda *_a: None)
        self.assertFalse(any(s.level == "crit" for s in restarted.run(ctx2)))

    def test_pagination_sees_later_page_and_error_does_not_delete(self):
        import radar.probes.discover as mod
        old = mod.PER_PAGE
        mod.PER_PAGE = 1
        try:
            http = FakeHttp(pages={"1": [_repo("flap-sh/One")], "2": [_repo("flap-sh/Two")]})
            probe, ctx = self._probe(http)
            probe.run(ctx)
            http.pages["2"].append(_repo("flap-sh/Three"))
            found = [s for s in probe.run(ctx) if s.kind == "new" and s.level == "crit"]
            self.assertEqual([s.payload["repo"] for s in found], ["Three"])
            http.fail_page = 2
            failed = probe.run(ctx)
            self.assertFalse(any(s.kind == "gone" for s in failed))
            self.assertIsNotNone(ctx.state.get("github-discover:FLAP", "repo:flap-sh/Three"))
        finally:
            mod.PER_PAGE = old

    def test_rate_limit_and_not_modified_do_not_alert(self):
        http = FakeHttp(pages={"1": [_repo("flap-sh/One")]}, fail_page="rate")
        probe, ctx = self._probe(http)
        self.assertEqual(probe.run(ctx), [])
        self.assertIsNone(ctx.state.get_meta("discover_baseline:flap-sh"))
        self.assertEqual(ctx.state.get_meta("discover_backoff_until"), "1900000000")
        ctx.state.set_meta("discover_backoff_until", "0")
        http.fail_page = None
        self.assertTrue(any(s.kind == "baseline" for s in probe.run(ctx)))
        signals = probe.run(ctx)
        self.assertFalse(any(s.level == "crit" for s in signals))
        self.assertTrue(any(call[1].get("If-None-Match") for call in http.calls))

    def test_doc_clue_does_not_promote_community_or_malicious_links(self):
        url = "https://four-meme.gitbook.io/four.meme/developer/openfour-integration"
        page = "Github repos: https://github.com/four-meme-community/openfour-docs javascript:alert(1) https://github.com/not-official/new"
        http = FakeHttp(docs={url: page})
        probe, ctx = self._probe(http, owners=[], doc_clues=[{
            "project": "four.meme", "url": url, "allowed_logins": [],
        }])
        first = probe.run(ctx)
        self.assertTrue(any(s.kind == "baseline" for s in first))
        self.assertFalse(any(s.level == "crit" for s in first))
        http.docs[url] = page + " https://github.com/not-official/another <script>"
        second = probe.run(ctx)
        infos = [s for s in second if s.level == "info" and s.kind == "new"]
        self.assertEqual(len(infos), 1)
        self.assertIn("未核实", infos[0].title)
        self.assertEqual(infos[0].url, "")
        self.assertNotIn("four-meme-community", infos[0].title)
        http.docs.pop(url)
        self.assertEqual(probe.run(ctx), [])
        self.assertIsNotNone(ctx.state.get("github-discover:four.meme", "clue:not-official/another"))


if __name__ == "__main__":
    unittest.main()
