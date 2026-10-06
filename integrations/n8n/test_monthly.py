"""Monthly rollover, correction, debouncing and delivery tests; no mail."""

import json
import tempfile
import unittest
from pathlib import Path

from fane.flow.report import Reports


class MonthlyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/monthly-report.json").write_text(
            json.dumps({"start_month": "2026-01", "settle_seconds": 600})
        )
        self.time = 1000
        self.report = Reports(
            root=self.root,
            now=lambda: "2026-10",
            clock=lambda: self.time,
            ledger={"2026-08": "August", "2026-09": "September", "2026-10": "October"},
        )
        self.report.facts = {month: {"validated": True} for month in self.report.ledger}
        self.report.notice()
        self.time += 601

    def tearDown(self):
        self.report.db.close()
        self.temp.cleanup()

    def claim(self):
        return self.report.prepare({"analysisMonth": "2026-09"})

    def payload(self, claim):
        return {
            **claim,
            "report": {
                "analysisMonth": "2026-09",
                "email_html": "<p>Fixture</p>",
                "email_text": "Fixture",
                "new_actions": [],
                "evaluations": [],
            },
        }

    def deliver(self, claim):
        self.assertTrue(self.report.store(self.payload(claim))["stored"])
        self.report.begin(claim)
        return self.report.sent(
            {**claim, "messageId": "fixture", "accepted_count": 1, "rejected_count": 0}
        )

    def change(self, month, text):
        self.report.ledger[month] = text
        self.report.notice()
        self.time += 601

    def test_atomic_claim_and_dry_run(self):
        self.assertEqual(
            self.report.prepare({"analysisMonth": "2026-09", "dryRun": True})["reason"],
            "dry-run",
        )
        first = self.claim()
        self.assertTrue(first["eligible"])
        self.assertEqual(self.claim()["reason"], "in-progress")
        self.report.release({**first, "claimToken": "wrong"})
        self.assertEqual(self.claim()["reason"], "in-progress")
        self.report.release(first)
        self.assertTrue(self.claim()["eligible"])

    def test_requires_rollover_and_waits_for_continuous_updates(self):
        self.report.db.execute(
            "UPDATE activity SET value='2026-09' WHERE key='updated_in'"
        )
        self.report.db.commit()
        self.assertEqual(self.claim()["reason"], "awaiting-rollover")
        self.report.notice()
        self.time += 601
        claim = self.claim()
        self.assertTrue(claim["eligible"])
        self.report.release(claim)
        # Check a separate unclaimed period to prove the quiet interval resets.
        self.change("2026-08", "first edit")
        self.report.ledger["2026-08"] = "second edit"
        self.report.notice()
        self.assertEqual(self.report.check("2026-08"), "settling")
        self.time += 599
        self.assertEqual(self.report.check("2026-08"), "settling")
        self.time += 1
        self.assertIsNone(self.report.check("2026-08"))

    def test_changed_current_or_previous_snapshot_releases_claim(self):
        for month in ["2026-08", "2026-09"]:
            claim = self.claim()
            self.assertTrue(claim["eligible"])
            self.report.ledger[month] += " correction"
            self.assertFalse(self.report.store(self.payload(claim))["stored"])
            self.report.notice()
            self.time += 601

    def test_fixme_stops_generation_and_retains_prior_receipt(self):
        claim = self.claim()
        self.deliver(claim)
        self.change("2026-09", "FIXME correction")
        self.assertEqual(self.claim()["reason"], "fixme")
        self.assertEqual(
            self.report.db.execute(
                "SELECT status FROM reports WHERE month=?", ("2026-09",)
            ).fetchone()[0],
            "sent",
        )

    def test_delivered_correction_is_a_revision_and_keeps_history(self):
        first = self.claim()
        self.deliver(first)
        self.assertEqual(self.claim()["reason"], "already-generated")
        self.change("2026-09", "Additional bank expense")
        second = self.claim()
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["reportMode"], "revision")
        self.report.release(second)
        self.assertEqual(
            self.report.db.execute(
                "SELECT revision FROM reports WHERE month=?", ("2026-09",)
            ).fetchone()[0],
            1,
        )
        second = self.claim()
        self.deliver(second)
        self.assertEqual(
            self.report.db.execute(
                "SELECT COUNT(*) FROM history WHERE month=?", ("2026-09",)
            ).fetchone()[0],
            2,
        )
        self.assertEqual(self.claim()["reason"], "already-generated")

    def test_formatted_text_with_same_financial_hash_does_not_resend(self):
        self.report.hashes = {
            "2026-08": "economic-aug",
            "2026-09": "economic-sep",
            "2026-10": "economic-oct",
        }
        self.report.notice()
        self.time += 601
        self.deliver(self.claim())
        self.report.ledger["2026-09"] = "  Different formatting ; comment"
        self.assertEqual(self.report.notice()["changed_months"], 0)
        self.assertEqual(self.claim()["reason"], "already-generated")

    def test_delivery_uncertain_or_rejected_never_auto_retries(self):
        claim = self.claim()
        self.report.store(self.payload(claim))
        self.assertEqual(self.claim()["reason"], "delivery-pending")
        self.report.begin(claim)
        with self.assertRaises(ValueError):
            self.report.begin(claim)
        with self.assertRaises(ValueError):
            self.report.sent({**claim, "accepted_count": 0, "rejected_count": 1})
        self.report.release(claim)
        self.time += 100000
        self.assertEqual(self.claim()["reason"], "delivery-pending")
        self.change("2026-09", "New data while receipt uncertain")
        self.assertEqual(self.claim()["reason"], "delivery-pending")

    def test_bootstrap_existing_reports_does_not_send_again(self):
        with self.report.db:
            self.report.db.execute(
                "INSERT INTO reports(month,status,report_json) VALUES('2026-09','sent','{}')"
            )
        self.report.bootstrap()
        self.time += 601
        self.assertEqual(self.claim()["reason"], "already-generated")
        self.assertEqual(
            self.report.db.execute("SELECT COUNT(*) FROM history").fetchone()[0], 1
        )

    def test_edit_between_save_and_send_cancels_unsent_report(self):
        claim = self.claim()
        self.report.store(self.payload(claim))
        self.report.ledger["2026-09"] = "Changed before SMTP"
        self.assertFalse(self.report.begin(claim)["eligible"])
        self.report.notice()
        self.time += 601
        self.assertTrue(self.claim()["eligible"])

    def test_calendar_alone_does_not_close_but_next_month_update_does(self):
        self.report.now = lambda: "2026-11"
        self.assertEqual(
            self.report.prepare({"analysisMonth": "2026-10"})["reason"],
            "awaiting-rollover",
        )
        self.report.notice()
        self.assertTrue(self.report.prepare({"analysisMonth": "2026-10"})["eligible"])


if __name__ == "__main__":
    unittest.main()
