"""Delivery-state regression tests with fictional data; no network or mail."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backfill


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.batch = self.root / "state/monthly-reports/backfill/test"
        self.batch.mkdir(parents=True)
        self.patch = patch.multiple(backfill, ROOT=self.root, BATCH=self.batch)
        self.patch.start()
        self.month = "2026-09"
        self.report = {
            "analysisMonth": self.month,
            "email_html": "<p>Fixture</p>",
            "email_text": "Fixture",
            "template_version": 2,
        }
        backfill.write(
            "snapshot.json", {"ledger": {"2026-09": "fixture", "2026-10": "partial"}}
        )
        db = sqlite3.connect(self.root / "state/monthly-reports/reports.sqlite")
        db.execute(
            "CREATE TABLE reports(month TEXT PRIMARY KEY,status TEXT,token TEXT,source_hash TEXT,generated_at TEXT,sent_at TEXT,report_json TEXT)"
        )
        db.close()
        self.seed(self.month)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def seed(self, month):
        self.report["analysisMonth"] = month
        backfill.write(
            "manifest.json",
            {
                "asOf": "2026-10-06",
                "selected": month,
                "months": {month: {"status": "ready", "generatedAt": "fixture"}},
            },
        )
        backfill.write(month + ".json", {"subject": "Fixture", "report": self.report})

    def sent(self):
        backfill.operate("begin")
        return backfill.operate(
            "sent",
            request={
                "accepted_count": 1,
                "rejected_count": 0,
                "messageId": "fixture-id",
            },
        )

    def rows(self):
        with sqlite3.connect(self.root / "state/monthly-reports/reports.sqlite") as db:
            return db.execute("SELECT month,status,report_json FROM reports").fetchall()

    def test_uncertain_delivery_and_sent_delivery_cannot_resend(self):
        backfill.operate("begin")
        with self.assertRaises(AssertionError):
            backfill.operate("begin")
        with self.assertRaises(AssertionError):
            backfill.operate(
                "sent",
                request={"accepted_count": 0, "rejected_count": 1, "messageId": ""},
            )
        self.assertEqual(
            backfill.read("manifest.json")["months"][self.month]["status"], "sending"
        )
        backfill.operate(
            "sent",
            request={
                "accepted_count": 1,
                "rejected_count": 0,
                "messageId": "fixture-id",
            },
        )
        with self.assertRaises(AssertionError):
            backfill.operate("begin")
        self.assertEqual(self.rows()[0][:2], (self.month, "sent"))

    def test_partial_report_does_not_complete_month(self):
        self.seed("2026-10")
        self.sent()
        self.assertEqual(self.rows(), [])

    def test_existing_sent_report_is_preserved(self):
        with sqlite3.connect(self.root / "state/monthly-reports/reports.sqlite") as db:
            db.execute(
                "INSERT INTO reports(month,status,report_json) VALUES(?,'sent','original')",
                (self.month,),
            )
        self.sent()
        self.assertEqual(self.rows(), [(self.month, "sent", "original")])


if __name__ == "__main__":
    unittest.main()
