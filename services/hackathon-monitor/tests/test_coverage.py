import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hackathon.engine import ATTACHED_KINDS, Store
from hackathon.main import install_configured
from hackathon.publish import _ecosystem
from hackathon.sources.external_sources import discover_external_catalog, discover_external_live
from hackathon.sources.solana_source import parse_directory


class CoverageTests(unittest.TestCase):
    def test_solana_directory_keeps_completed_and_funding_events(self):
        payload = json.dumps({
            "initialHackathons": [
                {"id": "a", "slug": "stocklana", "title": "Stocklana", "status": "completed", "hidden": False},
                {"id": "b", "slug": "consumer-apps", "title": "Consumer Apps", "status": "funding", "hidden": False},
                {"id": "c", "slug": "secret", "title": "Secret", "status": "completed", "hidden": True},
            ],
            "initialStatuses": {"a": "completed", "b": "funding", "c": "completed"},
        })
        html = "<script>self.__next_f.push(" + json.dumps([1, payload]) + ")</script>"
        found = {row["url"]: row for row in parse_directory(html)}
        self.assertEqual(found["https://hackathons.solana.com/hackathons/stocklana"]["event_status"], "completed")
        self.assertEqual(found["https://hackathons.solana.com/hackathons/consumer-apps"]["event_status"], "funding")
        self.assertNotIn("https://hackathons.solana.com/hackathons/secret", found)

    def test_superteam_live_failure_keeps_the_catalog_and_announced_tracks(self):
        def fetch(url, timeout):
            if url.endswith("/earn"):
                return '<html>Superteam Earn <a href="/earn/hackathon/crypto-worlds-fair">fair</a></html>'
            if "deadline=" in url:
                raise OSError("HTTP 500")
            if "/api/listings/live?" in url:
                raise OSError("HTTP 500")
            if "/api/listings?" in url:
                return json.dumps([
                    {"type": "hackathon", "slug": "announced-track", "title": "Announced Track", "isWinnersAnnounced": True},
                    {"type": "hackathon", "slug": "open-track", "title": "Open Track", "isWinnersAnnounced": False},
                ])
            raise OSError(url)
        catalog = discover_external_catalog(5, fetch)
        live = discover_external_live(5, fetch)
        self.assertEqual(catalog[0]["url"], "https://superteam.fun/earn/hackathon/crypto-worlds-fair")
        self.assertIn("https://superteam.fun/earn/listing/announced-track", {row["url"] for row in live})
        self.assertIn("https://superteam.fun/earn/listing/open-track", {row["url"] for row in live})

    def test_linked_winner_posts_and_side_tracks_are_attached(self):
        self.assertIn("bnb-news", ATTACHED_KINDS)
        self.assertIn("external", ATTACHED_KINDS)
        self.assertIn("dorahacks", ATTACHED_KINDS)

    def test_a_pin_outside_manual_sources_is_installed(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        store = Store(Path(temporary.name) / "pins.sqlite3")
        self.addCleanup(store.close)
        install_configured(store, {
            "manual_sources": [],
            "pins": [{"kind": "bnb_blog", "slug": "meet-the-winners-of-bnb-hack-ai-trading-agent-edition"}],
        })
        self.assertIsNotNone(store.source(
            "https://www.bnbchain.org/en/blog/meet-the-winners-of-bnb-hack-ai-trading-agent-edition"
        ))

    def test_missing_chain_is_not_called_bsc(self):
        self.assertEqual(_ecosystem(None), "unknown")
        self.assertEqual(_ecosystem(""), "unknown")
        self.assertEqual(_ecosystem("BSC"), "bnb")
        self.assertEqual(_ecosystem("SOL"), "solana")


if __name__ == "__main__":
    unittest.main()
