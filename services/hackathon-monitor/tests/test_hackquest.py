"""HackQuest official links come from labeled blurbs and structured projectLinks. No network."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hackathon.sources.hackquest_source import project


def entry(**extra):
    row = {"id": "p1", "name": "Sample", "alias": "Sample", "tracks": ["DeFi"]}
    row.update(extra)
    return row


class HackQuestLinksTest(unittest.TestCase):
    def test_structured_x_and_mvp_links_are_stored_as_official_urls(self):
        item = project(entry(
            name="Prex", alias="Prex",
            description="<p>PREX is an AI trading agent platform.</p>",
            projectLinks={"xLink": "https://x.com/No_tariff3", "mvpLink": "https://prex.best/"},
        ))
        self.assertEqual(item["twitter"], "https://x.com/No_tariff3")
        self.assertEqual(item["website"], "https://prex.best/")
        self.assertNotIn(" ", item["twitter"])

    def test_labeled_blurb_links_still_win_over_structured_fields(self):
        item = project(entry(
            description=(
                '<p>Official Website: <a href="https://astarter.io/">https://astarter.io/</a></p>'
                '<p>Official X: <a href="https://twitter.com/AstarterDefiHub">Astarter</a></p>'
            ),
            projectLinks={"xLink": "https://x.com/someoneelse", "mvpLink": "https://demo.example/"},
        ))
        self.assertEqual(item["website"], "https://astarter.io/")
        self.assertEqual(item["twitter"], "https://x.com/AstarterDefiHub")

    def test_missing_official_x_stays_empty(self):
        item = project(entry(
            description="<p>Only a product, no account.</p>",
            projectLinks={"xLink": "", "mvpLink": "https://guard.coingraph.ai"},
        ))
        self.assertEqual(item["website"], "https://guard.coingraph.ai")
        self.assertNotIn("twitter", item)

    def test_project_without_any_official_link_stays_blank(self):
        item = project(entry(description="<p>A short public intro.</p>", projectLinks={"xLink": "", "mvpLink": ""}))
        self.assertNotIn("website", item)
        self.assertNotIn("twitter", item)
        self.assertIn("info", item)

    def test_non_official_or_unusable_structured_urls_are_dropped(self):
        item = project(entry(
            description="",
            projectLinks=json.dumps({
                "xLink": "https://example.com/not-x",
                "mvpLink": "https://github.com/example/repo",
                "website": "https://crewtopia.example/",
                "twitterLink": "https://x.com/CrewtopiaAI/status/1",
            }),
        ))
        self.assertEqual(item["twitter"], "https://x.com/CrewtopiaAI")
        self.assertEqual(item["website"], "https://crewtopia.example/")


if __name__ == "__main__":
    unittest.main()
