"""Financial snapshot and bill archive contracts using fictional local data."""
from decimal import Decimal
import tempfile
import unittest
import zipfile
from pathlib import Path

from fane.bill.archive import unpack
from fane.flow.snapshot import snapshot


class FlowTests(unittest.TestCase):
    def test_snapshot_keeps_facts_and_ignores_formatting_but_detects_amounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.bean"
            source = '2026-01-01 open Assets:Bank CNY\n2026-01-01 open Expenses:Food CNY\n2026-09-01 * "Shop" "Lunch"\n  Expenses:Food 12.34 CNY\n  Assets:Bank -12.34 CNY\n'
            path.write_text(source)
            before = snapshot(path)
            path.write_text(source.replace('"Lunch"', '"Updated note"').replace("12.34", "12.340") + "; comment\n")
            after = snapshot(path)
            self.assertEqual(before["hashes"], after["hashes"])
            self.assertEqual(Decimal(before["facts"]["2026-09"]["totals"]["expenses"]["net"]["CNY"]), Decimal(after["facts"]["2026-09"]["totals"]["expenses"]["net"]["CNY"]))
            path.write_text(source.replace("12.34", "15.00"))
            self.assertNotEqual(before["hashes"], snapshot(path)["hashes"])

    def test_archive_accepts_one_expected_file_and_rejects_extra_or_wrong_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bill.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("bill.csv", "fixture")
            self.assertEqual(unpack(path, "csv"), b"fixture")
            with self.assertRaises(ValueError):
                unpack(path, "xlsx")
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("other.csv", "fixture")
            with self.assertRaises(ValueError):
                unpack(path, "csv")
