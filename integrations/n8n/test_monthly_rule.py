"""Automatic monthly limits, real export coverage, and reminder deduplication."""

import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from fane.flow.coverage import missing_sources
from fane.flow.report import Reports


class MonthlyRuleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/monthly-report.json").write_text(
            json.dumps(
                {
                    "start_month": "2026-01",
                    "automatic_enabled": True,
                    "required_sources": ["alipay", "wechat"],
                }
            )
        )
        self.time = datetime(
            2026, 10, 3, 10, tzinfo=ZoneInfo("Asia/Shanghai")
        ).timestamp()
        self.reports = Reports(
            root=self.root,
            now=lambda: "2026-10",
            clock=lambda: self.time,
            ledger={"2026-08": "Old", "2026-09": "Fixture"},
        )
        self.addCleanup(self.reports.db.close)

    def bill(
        self,
        provider,
        start="2026-09-01 00:00:00",
        end="2026-09-30 23:59:59",
        name="bill",
    ):
        folder = self.root / "data/bills" / provider
        folder.mkdir(parents=True, exist_ok=True)
        text = f"起始时间：[{start}] 终止时间：[{end}]"
        path = folder / (name + (".csv" if provider == "alipay" else ".xlsx"))
        if provider == "alipay":
            path.write_text(text + "\n交易时间,金额\n", encoding="utf-8-sig")
        else:
            workbook = Workbook()
            workbook.active.append([text])
            workbook.active.append(["交易时间", "金额"])
            workbook.save(path)
        path.with_name(path.name + ".md5").write_text(
            hashlib.md5(path.read_bytes()).hexdigest()
        )
        return path

    def complete(self):
        self.bill("alipay")
        self.bill("wechat")

    def claim(self, month="2026-09", **extra):
        return self.reports.prepare(
            {"analysisMonth": month, "automatic": True, **extra}
        )

    def test_partial_export_and_changed_file_are_not_complete(self):
        self.bill("alipay", end="2026-09-15 23:59:59")
        path = self.bill("wechat")
        self.assertEqual(
            missing_sources(self.root, "2026-09", ["alipay", "wechat"]), ["alipay"]
        )
        path.write_bytes(path.read_bytes() + b"changed")
        self.assertEqual(
            missing_sources(self.root, "2026-09", ["alipay", "wechat"]),
            ["alipay", "wechat"],
        )

    def test_contiguous_weekly_exports_cover_month_but_gap_does_not(self):
        self.bill("alipay", end="2026-09-15 23:59:59", name="first")
        self.bill("alipay", start="2026-09-16 00:00:00", name="second")
        self.assertEqual(missing_sources(self.root, "2026-09", ["alipay"]), [])
        self.bill("alipay", start="2026-09-16 00:00:01", name="second")
        self.assertEqual(missing_sources(self.root, "2026-09", ["alipay"]), ["alipay"])

    def test_monthly_boundary_and_only_previous_month(self):
        self.complete()
        self.time -= 1
        self.assertEqual(self.reports.auto_plan(), [])
        self.time += 1
        self.assertEqual(
            self.reports.auto_plan(),
            [{"analysisMonth": "2026-09", "automatic": True, "dryRun": False}],
        )
        self.assertEqual(
            self.claim("2026-08")["reason"], "automatic-only-previous-month"
        )

    def test_missing_reminded_once_then_arrival_becomes_ready(self):
        notice = self.reports.auto_plan()[0]
        self.assertEqual(notice["notice"], "missing-bills:alipay,wechat")
        self.assertEqual(self.reports.auto_plan(), [])
        self.complete()
        self.assertTrue(self.reports.auto_plan()[0]["automatic"])

    def test_failure_release_restart_and_ledger_edit_cannot_spend_again(self):
        self.complete()
        first = self.claim()
        self.assertTrue(first["eligible"])
        self.assertEqual(self.claim()["reason"], "automatic-attempt-used")
        self.reports.release(first)
        self.time += 100000
        self.reports.ledger["2026-09"] = "Edited fixture"
        self.assertEqual(self.reports.auto_plan(), [])
        second = Reports(
            root=self.root,
            now=lambda: "2026-10",
            clock=lambda: self.time,
            ledger=self.reports.ledger,
        )
        try:
            self.assertEqual(
                second.prepare({"analysisMonth": "2026-09", "automatic": True})[
                    "reason"
                ],
                "automatic-attempt-used",
            )
        finally:
            second.db.close()

    def test_sent_old_report_is_not_automatically_revised(self):
        with self.reports.db:
            self.reports.db.execute(
                "INSERT INTO reports(month,status,semantic_hash) VALUES('2026-09','sent','old')"
            )
        self.assertEqual(self.reports.auto_plan(), [])
        self.assertEqual(self.claim()["reason"], "already-generated")

    def test_dry_run_does_not_consume_notice_or_model_allowance(self):
        self.assertTrue(self.reports.auto_plan(True)[0]["dryRun"])
        self.assertEqual(
            self.reports.db.execute(
                "SELECT COUNT(*) FROM automatic_notices"
            ).fetchone()[0],
            0,
        )
        self.complete()
        self.assertEqual(self.claim(dryRun=True)["reason"], "dry-run")
        self.assertEqual(
            self.reports.db.execute(
                "SELECT COUNT(*) FROM automatic_attempts"
            ).fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
