"""Parsers, archive retention, and honest empty states. No network."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hackathon.classify import announcement_in_scope, blog_role, classify_index_program
from hackathon.collect import best_match, run_cycle
from hackathon.parse_announcement import merge_articles, parse_article
from hackathon.parse_blog import parse_post
from hackathon.parse_program import program_to_draft
from hackathon.snapshot import build_snapshot, phase_of
from hackathon.store import Store

NOW = datetime(2026, 11, 27, 12, 49, tzinfo=timezone.utc)
CODE = "95f5dbe0ea674a48a739b59e046648bf"


def article(title, paragraphs, links):
    children = []
    for text in paragraphs:
        children.append({"node": "element", "tag": "p", "child": [{"node": "text", "text": text}]})
    for label, href in links:
        children.append({"node": "element", "tag": "a", "attr": {"href": href}, "child": [{"node": "text", "text": label}]})
    return {"code": "000000", "data": {"title": title, "body": {"node": "root", "child": children}}}


ZH = article(
    "Agent ID黑客松：围绕Agent ID构建去中心化应用，赢取60,000 USDC奖励",
    [
        "币安钱包联合BNB智能链共同举办Agent ID黑客松。",
        "作品提交期：2026年11月18日16:00:00至2026年12月09日16:00:00（东八区时间）",
        "评审期：2026年12月09日16:00:00至2026年12月17日16:00:00（东八区时间）",
        "公示期：2026年12月17日16:00:00至2026年12月20日16:00:00（东八区时间）",
        "本次活动总奖励为 60,000 USDC。",
    ],
    [
        ("立即提交作品", "https://app.binance.com/uni-qr/user-survey/fb26d2bd25e04329b1ba77c7b3811d23"),
        ("提交 X 链接至社区传播", "https://app.binance.com/uni-qr/user-survey/ff6832f8d2984af289068c9450a3c98c"),
    ],
)
EN = article(
    "Agent ID Hackathon: Build dApps Around Agent ID to Win 60,000 USDC",
    [
        "Submission Period: 2026-11-18 08:00 (UTC) to 2026-12-09 08:00 (UTC)",
        "Internal Review Period: 2026-12-09 08:00 (UTC) to 2026-12-17 08:00 (UTC)",
        "Public Review Period: 2026-12-17 08:00 (UTC) to 2026-12-20 08:00 (UTC)",
    ],
    [("Submit your project", "https://app.binance.com/uni-qr/user-survey/fb26d2bd25e04329b1ba77c7b3811d23")],
)

PROGRAM = {
    "slug": "tokenized-stocks",
    "title": "BNB Hackathon: Tokenized Stocks Edition",
    "publish": True,
    "status": "Ended",
    "timezone": "UTC +0",
    "start": "2026-09-16T12:00:00",
    "end": "2026-10-11T12:00:00",
    "description": "Tokenized stocks hackathon on BSC.",
    "prize_pool": 20000,
    "location_online": True,
    "submit_project_url": "https://forms.gle/yToDUzaDMwWnq6R6A",
    "winner_layer": [1],
    "date_updated": "2026-11-05T13:21:16.000Z",
}
DETAIL = {
    **PROGRAM,
    "winner_layer": [{
        "layer1": "Main",
        "layer2": "1st",
        "winners": [{"id": 7, "name": "Moi", "desc": "A submitted winner", "demo": "https://example.com/moi"}],
    }],
}
FUTURE = {
    "slug": "next-open-hack",
    "title": "BNB Hackathon: Next Open Edition",
    "publish": True,
    "status": "Upcoming",
    "timezone": "UTC +0",
    "start": "2026-12-01T12:00:00",
    "end": "2026-12-20T12:00:00",
    "description": "Another official hackathon.",
    "prize_pool": 1000,
    "location_online": True,
    "winner_layer": [],
    "date_updated": "2026-11-27T00:00:00.000Z",
}
RELATED = {
    "slug": "smart-money-era-set-and-earn",
    "title": "The Smart Money Era: Set and Earn",
    "publish": True,
    "status": "Ended",
    "timezone": "UTC +0",
    "start": "2026-10-01T00:00:00",
    "end": "2026-11-05T00:00:00",
    "description": "The campaign opens shortlisted marketplaces.",
    "prize_pool": 10000,
    "location_online": True,
    "winner_layer": [],
    "date_updated": "2026-09-30T08:30:23.000Z",
}

BANGKOK = """
<h1>BNB Bangkok: Build, Demo, and Pitch</h1>
<p>BNB Chain is hosting a Hackathon and Demo Night in Bangkok during November 25–27, 2026.</p>
<p>Join us at Park Hyatt Bangkok on Friday, November 27, from 15:00–18:00 for live project demos.</p>
<table><tr><th>Date</th><th>Stage</th><th>What to Expect</th></tr>
<tr><td>November 25</td><td>Developer Track Begins</td><td>The 36-hour build period starts in the evening.</td></tr></table>
<table><tr><td>1st</td><td>$5,000 USD</td></tr><tr><td>2nd</td><td>$3,000 USD</td></tr></table>
<a href="https://luma.com/n5y1y7cu">Register</a>
"""
WINNERS = """
<h1>Meet the Winners of BNB Hack: Tokenized Stocks Edition with Binance Web3 Wallet</h1>
<p>Five submissions stood out. Here are the winning projects.</p>
<p>Main Track Winners: Tokenized Stock Products and Agents</p>
<p>1st Place ($6,000): Moi</p>
<p>2nd Place ($4,000): 4lpha</p>
"""


def page(props):
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": props}}) + "</script>"


class FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def fetch(self, url, headers=None):
        self.urls.append(url)
        if url not in self.routes:
            raise AssertionError(url)
        body = self.routes[url]
        if callable(body):
            body = body(headers or {})
        return 200, body if isinstance(body, bytes) else body.encode()


def cfg():
    return {
        "detail_refresh_seconds": 0,
        "blog_pages_per_cycle": 1,
        "announcement_pages_per_cycle": 2,
        "sources": {
            "hackathon_index": "https://www.bnbchain.org/en/hackathons",
            "blog": "https://www.bnbchain.org/en/blog?page={page}",
            "binance_catalog": "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId={catalog}&pageNo={page}&pageSize=20",
            "binance_article": "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}",
            "catalogs": [93],
        },
        "pins": [
            {"kind": "binance_article", "code": CODE},
            {"kind": "bnb_blog", "slug": "bnb-bangkok-build-demo-and-pitch"},
        ],
    }


def routes(programs):
    catalog = json.dumps({"data": {"articles": [
        {"code": "trade", "title": "Binance Alpha Trading Competition: Trade and Share"},
        {"code": "week", "title": "Binance Blockchain Week: Share Your Experience"},
        {"code": CODE, "title": "Agent ID Hackathon: Build dApps"},
    ]}})
    return {
        "https://www.bnbchain.org/en/hackathons": page({"initialState": {"cms": {"hackathonPrograms": programs}}}),
        "https://www.bnbchain.org/en/hackathons/tokenized-stocks": page({"initialState": {"cms": {"activeHackathonProgram": DETAIL}}}),
        "https://www.bnbchain.org/en/hackathons/smart-money-era-set-and-earn": page({"initialState": {"cms": {"activeHackathonProgram": RELATED}}}),
        "https://www.bnbchain.org/en/hackathons/next-open-hack": page({"initialState": {"cms": {"activeHackathonProgram": FUTURE}}}),
        "https://www.bnbchain.org/en/blog?page=1": page({"initialState": {"base": {"postData": {"data": [
            {"slug": "bnb-bangkok-build-demo-and-pitch", "title": "BNB Bangkok: Build, Demo, and Pitch", "excerpt": "Join BNB Chain’s Bangkok hackathon and Demo Night, November 25–27, 2026."},
            {"slug": "meet-the-winners-of-bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet", "title": "Meet the Winners of BNB Hack: Tokenized Stocks Edition with Binance Web3 Wallet", "excerpt": "Five submissions stood out in BNB Hack."},
            {"slug": "bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet", "title": "BNB Hack: Tokenized Stocks Edition, with Binance Web3 Wallet", "excerpt": "A BNB Hack announcement for the tokenized stocks edition."},
            {"slug": "37th-bnb-burn", "title": "37th BNB Burn", "excerpt": "Quarterly burn."},
        ], "meta": {"pagination": {"pages": 3}}}}}}),
        "https://www.bnbchain.org/en/blog/bnb-bangkok-build-demo-and-pitch": BANGKOK,
        "https://www.bnbchain.org/en/blog/meet-the-winners-of-bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet": WINNERS,
        "https://www.bnbchain.org/en/blog/bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet": "<h1>BNB Hack: Tokenized Stocks Edition, with Binance Web3 Wallet</h1><p>This hackathon ran earlier.</p>",
        "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId=93&pageNo=1&pageSize=20": catalog,
        "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId=93&pageNo=2&pageSize=20": json.dumps({"data": {"articles": []}}),
        "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=" + CODE: lambda headers: json.dumps(ZH if headers.get("lang") == "zh-CN" else EN),
    }


class MonitorTests(unittest.TestCase):
    def test_announcement_times_match_across_languages_and_form_is_not_a_gallery(self):
        zh = parse_article(ZH, CODE, "zh-CN")
        en = parse_article(EN, CODE, "en")
        draft = merge_articles(CODE, zh, en)
        by_key = {item.key: item for item in draft.milestones}
        self.assertEqual(by_key["submission"].start_utc, "2026-11-18T08:00:00Z")
        self.assertEqual(by_key["submission"].end_utc, "2026-12-09T08:00:00Z")
        self.assertEqual(by_key["review"].end_utc, "2026-12-17T08:00:00Z")
        self.assertEqual(by_key["announcement"].end_utc, "2026-12-20T08:00:00Z")
        self.assertIn("2026-11-18 16:00", by_key["submission"].display)
        self.assertIn("北京时间（UTC+8）", by_key["submission"].display)
        self.assertEqual(draft.submission_state, "private_form")
        self.assertEqual(draft.projects, [])
        self.assertIn("不是公开项目", draft.submission_note)
        self.assertEqual(draft.results_state, "not_published")
        self.assertIn("60,000 USDC", draft.prize)
        self.assertTrue(any("社区传播" in link.label for link in draft.links))

    def test_program_keeps_winners_separate_from_missing_submissions(self):
        draft = program_to_draft(DETAIL)
        self.assertEqual(draft.classification, "hackathon")
        self.assertEqual(draft.official_status, "Ended")
        self.assertEqual(draft.start_utc, "2026-09-16T12:00:00Z")
        self.assertIn("20:00", draft.milestones[0].display)
        self.assertEqual(draft.submission_state, "private_form")
        self.assertEqual(draft.projects[0].name, "Moi")
        self.assertEqual(draft.projects[0].role, "winner")
        self.assertEqual(draft.results_state, "published")
        self.assertNotIn("sold out", draft.summary.lower())
        related = program_to_draft(RELATED)
        self.assertEqual(related.classification, "related")

    def test_bangkok_uses_published_dates_and_does_not_invent_capacity(self):
        draft = parse_post(BANGKOK, "bnb-bangkok-build-demo-and-pitch", "BNB Bangkok: Build, Demo, and Pitch", "Bangkok hackathon")
        window = next(item for item in draft.milestones if item.key == "window")
        demo = next(item for item in draft.milestones if item.key == "demo-night")
        self.assertIn("未写时刻", window.display)
        self.assertIn("2026-11-25", window.display)
        self.assertIn("2026-11-27 16:00 至 2026-11-27 19:00", demo.display)
        self.assertEqual(draft.submission_state, "private_form")
        self.assertEqual(draft.projects, [])
        self.assertEqual(draft.results_state, "not_published")
        blob = json.dumps(draft.__dict__, ensure_ascii=False, default=lambda item: item.__dict__)
        self.assertNotIn("sold out", blob.lower())
        self.assertNotIn("已满", blob)
        self.assertIn("$5,000 USD", draft.prize)
        self.assertTrue(any(item.label == "Developer Track Begins" for item in draft.milestones))
        self.assertIn("evening", next(item.display for item in draft.milestones if item.label == "Developer Track Begins"))

    def test_winner_post_does_not_become_a_submission_list(self):
        draft = parse_post(WINNERS, "meet-the-winners", "Meet the Winners of BNB Hack: Tokenized Stocks Edition", "BNB Hack")
        self.assertEqual([item.name for item in draft.projects], ["Moi", "4lpha"])
        self.assertTrue(all(item.role == "winner" for item in draft.projects))
        self.assertEqual(draft.submission_state, "not_published")
        self.assertIn("不是可核验的全部投稿", draft.submission_note)

    def test_noise_stays_out_and_archive_keeps_ended_events(self):
        self.assertFalse(announcement_in_scope("Binance Alpha Trading Competition: Trade and Share"))
        self.assertFalse(announcement_in_scope("Binance Blockchain Week: Share Your Experience"))
        self.assertTrue(announcement_in_scope("Agent ID Hackathon: Build dApps"))
        self.assertIsNone(blog_role("37th BNB Burn", "Quarterly burn."))
        self.assertEqual(blog_role("BNB Bangkok: Build, Demo, and Pitch", "Bangkok hackathon")[0] if False else blog_role("BNB Bangkok: Build, Demo, and Pitch", "Bangkok hackathon"), "event")
        self.assertEqual(classify_index_program("The Smart Money Era: Set and Earn")[0], "related")
        with self.subTest("cycle"):
            path = Path("/tmp") / (self.id().replace(".", "-") + ".sqlite3")
            path.unlink(missing_ok=True)
            store = Store(str(path))
            try:
                client = FakeClient(routes([PROGRAM, RELATED]))
                report = run_cycle(cfg(), client, store, NOW)
                self.assertGreaterEqual(report["index"], 2)
                self.assertEqual(report["announcements"], 1)
                snap = build_snapshot(store, NOW)
                by_id = {item["id"]: item for item in snap["events"]}
                self.assertIn("bnb-hackathon:tokenized-stocks", by_id)
                self.assertNotIn("binance:trade", by_id)
                self.assertNotIn("binance:week", by_id)
                stocks = by_id["bnb-hackathon:tokenized-stocks"]
                self.assertEqual(stocks["phase"], "ended")
                self.assertEqual(stocks["phase_basis"], "official_status")
                self.assertEqual(stocks["submission"]["state"], "private_form")
                self.assertEqual(stocks["submission"]["projects"], [])
                self.assertEqual(sorted(item["name"] for item in stocks["results"]["projects"]), ["4lpha", "Moi"])
                self.assertTrue(all(item["source_url"].startswith("https://") for item in stocks["results"]["projects"]))
                self.assertIn("bnb-blog:bnb-bangkok-build-demo-and-pitch", by_id)
                self.assertEqual(by_id["bnb-blog:bnb-bangkok-build-demo-and-pitch"]["phase"], "live")
                self.assertNotIn("bnb-blog:bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet", by_id)
                self.assertTrue(any(link["url"].endswith("/bnb-hack-tokenized-stocks-edition-with-binance-web3-wallet") for link in stocks["links"]))
                self.assertEqual(by_id["binance:" + CODE]["phase"], "live")
                self.assertEqual(by_id["binance:" + CODE]["results"]["projects"], [])
                self.assertTrue(snap["standing"])
                self.assertNotIn("37th-bnb-burn", client.urls.__str__())
                # The catalog event leaves the index and a new one appears. Nothing is deleted.
                client.routes["https://www.bnbchain.org/en/hackathons"] = page({"initialState": {"cms": {"hackathonPrograms": [FUTURE]}}})
                run_cycle(cfg(), client, store, NOW)
                snap = build_snapshot(store, NOW)
                by_id = {item["id"]: item for item in snap["events"]}
                self.assertIn("bnb-hackathon:tokenized-stocks", by_id)
                self.assertFalse(by_id["bnb-hackathon:tokenized-stocks"]["listed"])
                self.assertIn("没有再列出", by_id["bnb-hackathon:tokenized-stocks"]["missing_note"])
                self.assertEqual(by_id["bnb-hackathon:next-open-hack"]["phase"], "upcoming")
                self.assertIn("bnb-blog:bnb-bangkok-build-demo-and-pitch", by_id)
                self.assertIn("binance:" + CODE, by_id)
            finally:
                store.close()

    def test_unknown_window_is_not_called_ended(self):
        self.assertEqual(phase_of(None, None, None, NOW), ("unknown", "insufficient"))
        self.assertEqual(phase_of("Ended", "2026-12-01T00:00:00Z", "2026-12-02T00:00:00Z", NOW)[0], "ended")
        self.assertEqual(phase_of(None, "2026-12-01T00:00:00Z", "2026-12-02T00:00:00Z", NOW)[0], "upcoming")

    def test_winner_title_matches_the_catalog_event(self):
        rows = [{"id": "bnb-hackathon:tokenized-stocks", "title": "BNB Hackathon: Tokenized Stocks Edition"}]
        match = best_match("Meet the Winners of BNB Hack: Tokenized Stocks Edition with Binance Web3 Wallet", rows)
        self.assertEqual(match["id"], "bnb-hackathon:tokenized-stocks")
        self.assertIsNone(best_match("BNB Bangkok: Build, Demo, and Pitch", rows))
        tied = rows + [{"id": "bnb-blog:same-story", "title": "BNB Hack: Tokenized Stocks Edition, with Binance Web3 Wallet"}]
        self.assertEqual(best_match("BNB Hack: Tokenized Stocks Edition, with Binance Web3 Wallet", tied)["id"], "bnb-hackathon:tokenized-stocks")


if __name__ == "__main__":
    unittest.main()
