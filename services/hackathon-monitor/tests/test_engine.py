import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hackathon.engine import Store, publication_summary

EVENT = "https://example.com/hackathons/bsc-example"
GALLERY = EVENT + "/gallery"
RESULTS = EVENT + "/results"
FIRST = "2026-11-27T18:00:00+08:00"
SECOND = "2026-11-27T18:15:00+08:00"


class WatchStateTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "monitor.sqlite3")
        self.addCleanup(self.store.close)
        self.store.add_source(EVENT, GALLERY, "test", "Example BSC Hack")

    def test_idempotency_and_failure_preserve_last_good_data(self):
        result = {
            "submission_status": "published",
            "submissions": [{"id": "project-1", "name": "Project One", "url": GALLERY + "/1"}],
        }
        self.store.record(GALLERY, FIRST, result)
        self.store.record(GALLERY, SECOND, result)
        self.store.fail(GALLERY, SECOND, "HTTP 503")
        event = self.store.events()[0]
        self.assertEqual(event["findings"][0]["first_seen"], FIRST)
        self.assertEqual(len(event["findings"]), 1)
        self.assertEqual(event["sources"][0]["status"], "error")
        self.assertEqual(event["sources"][0]["last_success"], SECOND)

    def test_winner_and_submission_are_separate_and_time_keeps_provenance(self):
        self.store.add_source(EVENT, RESULTS, "test", "Example BSC Hack")
        self.store.record(GALLERY, FIRST, {
            "submission_status": "published",
            "submissions": [{"name": "Project One"}],
            "schedule": [{"kind": "submission_close", "label": "Submission closed", "time": "2026-11-27T10:00:00+08:00"}],
        })
        self.store.record(RESULTS, SECOND, {
            "winner_status": "published",
            "winners": [{"name": "Project One", "category": "Flap", "rank": "First Place"}],
            "published_at": "2026-11-27T18:12:00+08:00",
        })
        by_kind = {row["kind"]: row for row in self.store.events()[0]["findings"]}
        self.assertEqual(set(by_kind), {"submission", "winner"})
        self.assertIsNone(by_kind["submission"]["published_at"])
        self.assertEqual(by_kind["winner"]["published_at"], "2026-11-27T18:12:00+08:00")
        result = publication_summary(self.store.events()[0], datetime(2026, 11, 27, 11, tzinfo=timezone.utc))
        self.assertEqual(result["submission"]["elapsed_basis"], "first_seen")
        self.assertEqual(result["submission"]["elapsed_hours"], 8.0)
        self.assertEqual(result["winner"]["elapsed_basis"], "published_at")
        self.assertEqual(result["winner"]["elapsed_hours"], 8.2)

    def test_missing_list_is_not_a_published_empty_list(self):
        self.store.record(GALLERY, FIRST, {
            "submission_status": "unverified",
            "schedule": [{"kind": "results_expected", "label": "Reward Announcement", "time": "2026-11-27T20:00:00+08:00"}],
        })
        self.store.record(GALLERY, SECOND, {"submission_status": "unverified"})
        result = publication_summary(self.store.events()[0], datetime(2026, 11, 27, 11, tzinfo=timezone.utc))
        self.assertIsNone(result["submission"]["first_seen"])
        self.assertEqual(result["winner"]["expected_in_hours"], 1.0)
        self.assertEqual(self.store.events()[0]["findings"], [])



    def test_new_schedule_after_success_is_reported(self):
        self.store.record(GALLERY, FIRST, {"submission_status": "unverified"})
        alerts = self.store.record(GALLERY, SECOND, {
            "submission_status": "unverified",
            "schedule": [{"kind": "results_expected", "label": "Reward Announcement", "time": SECOND}],
        })
        self.assertEqual([alert["kind"] for alert in alerts], ["schedule"])


    def test_first_gallery_open_is_logged_without_individual_submission_alerts(self):
        self.store.record(GALLERY, FIRST, {"submission_status": "not_published"})
        first_items = [{"name": "SOL Project", "id": "p1", "chain": "SOL", "category": "Finance"}]
        result = self.store.record(GALLERY, SECOND, {"submission_status": "published",
                                                   "submissions": first_items})
        self.assertEqual([notice["kind"] for notice in result], ["gallery_opened"])
        next_items = first_items + [{"name": "Other-chain project", "id": "p2", "chain": "Base"}]
        self.assertEqual(self.store.record(GALLERY, SECOND, {"submission_status": "published",
                                                            "submissions": next_items}), [])
        self.assertEqual([row["chain"] for row in self.store.events()[0]["findings"]], ["Base", "SOL"])
        self.assertEqual([notice["kind"] for notice in self.store.updates()], ["gallery_opened"])

    def test_existing_results_after_restart_are_not_reissued(self):
        result = {"winner_status": "partial", "winners": [{"name": "Other-chain project",
                    "id": "p2", "chain": "Base", "category": "Main Track", "rank": "First Place"}]}
        self.store.record(GALLERY, FIRST, {"winner_status": "not_published"})
        self.assertEqual([notice["kind"] for notice in self.store.record(GALLERY, SECOND, result)], ["winner"])
        self.assertEqual(self.store.record(GALLERY, SECOND, result), [])
        self.assertEqual(self.store.updates()[0]["items"][0]["chain"], "Base")
        self.assertEqual(self.store.events()[0]["findings"][0]["chain"], "Base")

    def test_discovery_is_baselined_and_completed_history_is_skipped(self):
        from hackathon.engine import add_discovery
        active = [{"name": "Current BSC Event", "kind": "hackquest",
                   "url": "https://www.hackquest.io/hackathons/current", "event_status": "active"}]
        old = [{"name": "Old SOL Event", "kind": "hackquest", "event_status": "completed",
                "url": "https://www.hackquest.io/hackathons/old"}]
        baseline = "https://www.hackquest.io/hackathons"
        self.assertEqual(add_discovery(self.store, active + old, baseline, FIRST), [])
        self.assertIsNone(self.store.source(old[0]["url"]))
        new = [{"name": "New SOL Event", "kind": "solana", "event_status": "scheduled",
                "url": "https://hackathons.solana.com/hackathons/new", "chain": "SOL"}]
        changes = add_discovery(self.store, active + old + new, baseline, SECOND)
        self.assertEqual([x["kind"] for x in changes], ["new_event"])
        self.assertEqual(changes[0]["event"], "New SOL Event")
        self.assertEqual(add_discovery(self.store, active + old + new, baseline, SECOND), [])


    def test_completed_with_submissions_error_remains_retryable(self):
        payload = {"event_status": "completed", "submission_status": "error",
                   "winner_status": "published", "winners": [{"name": "Winner"}]}
        self.store.record(GALLERY, FIRST, payload)
        now = datetime.fromisoformat(FIRST)
        self.store.refresh_stages({EVENT}, now)
        self.assertEqual(self.store.events()[0]["stage"], "collection_incomplete")
        self.store.record(GALLERY, SECOND, {**payload, "submission_status": "published",
                                           "submissions": [{"id": "p1", "name": "Winner"}]})
        self.store.refresh_stages({EVENT}, now)
        self.assertEqual(self.store.events()[0]["stage"], "completed")

    def test_equivalent_publish_timestamps_do_not_trigger_change(self):
        result = {"schedule": [{"kind": "results_expected", "label": "Expected result", "time": FIRST}]}
        self.store.record(GALLERY, FIRST, result)
        result["schedule"][0]["time"] = "2026-11-27T10:00:00+00:00"
        self.assertEqual(self.store.record(GALLERY, SECOND, result), [])


if __name__ == "__main__":
    unittest.main()

