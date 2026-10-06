import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("bill", "classify", "subscriptions", "ledger", "query", "flow")


class ModulesTest(unittest.TestCase):
    def run_cli(self, base, *args, input=None, env=None):
        result = subprocess.run(
            [sys.executable, "-m", "fane", *map(str, args)],
            cwd=base,
            input=input,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": str(base),
                "FANE_STATE_HOME": str(base / "state"),
                **(env or {}),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def fixture(self, base):
        ledger = base / "main.bean"
        ledger.write_text(
            'option "operating_currency" "CNY"\n2026-01-01 open Assets:Bank CNY\n2026-01-01 open Expenses:Food CNY\n'
            '2026-01-02 * "Meal"\n  Expenses:Food 12.34 CNY\n  Assets:Bank -12.34 CNY\n'
        )
        config = base / "fane.yaml"
        config.write_text(
            f"default-minus-account: Assets:Bank\ndefault-plus-account: Expenses:Food\n"
            f"default-currency: CNY\nledger:\n  file: {ledger}\n"
        )
        plan = base / "subscriptions.json"
        plan.write_text("[]")
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "交易时间",
                "交易单号",
                "商户单号",
                "收/支",
                "交易对方",
                "商品",
                "金额(元)",
                "当前状态",
                "支付方式",
                "交易类型",
            ]
        )
        sheet.append(
            [
                "2026-01-02 12:00:00",
                "fixture",
                "/",
                "支出",
                "店",
                "午餐",
                "12.34",
                "支付成功",
                "零钱",
                "商户消费",
            ]
        )
        source = base / "bill.xlsx"
        workbook.save(source)
        return config, ledger, plan, source

    def test_each_feature_runs_when_all_other_features_are_physically_absent(self):
        for feature in FEATURES:
            with (
                self.subTest(feature=feature),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                shutil.copytree(
                    ROOT / "fane",
                    base / "fane",
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
                for other in set(FEATURES) - {feature}:
                    shutil.rmtree(base / "fane" / other)
                config, ledger, plan, source = self.fixture(base)
                self.run_cli(base, "--help")
                commands = {
                    "bill": ["convert", "-p", "wechat", "-s", source, "-f", "jsonl"],
                    "classify": ["classify", "extract", "--root", base],
                    "subscriptions": [
                        "sub",
                        "generate",
                        "--subscriptions",
                        plan,
                        "--json",
                    ],
                    "ledger": ["ledger", "export", "--meta"],
                    "query": ["query", "2026-01-01", "2026-01-31"],
                    "flow": ["flow", "--root", base, "sync"],
                }
                if feature == "flow":
                    (base / "config").mkdir()
                    (base / "config/n8n-sync.json").write_text(
                        '{"secret":"fixture","branch":"main"}'
                    )
                if feature == "classify":
                    (base / "journal").mkdir()
                    (base / "accounts/data").mkdir(parents=True)
                self.assertIsInstance(
                    json.loads(
                        self.run_cli(
                            base,
                            "-c",
                            config,
                            *commands[feature],
                            input='{"body":"e30=","signature":"invalid"}'
                            if feature == "flow"
                            else None,
                        )
                    ),
                    dict,
                )
                if feature == "classify":
                    # Applying an empty, complete batch still validates without ledger/ or bill/.
                    self.run_cli(
                        base,
                        "-c",
                        config,
                        "classify",
                        "apply",
                        "--root",
                        base,
                        "--write",
                        input='{"schema_version": 1, "decisions": []}',
                    )

    def test_shared_commands_work_with_every_feature_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(
                ROOT / "fane",
                base / "fane",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            for feature in FEATURES:
                shutil.rmtree(base / "fane" / feature)
            config = base / "fane.yaml"
            self.run_cli(base, "--help")
            self.run_cli(base, "--version")
            self.run_cli(base, "-c", config, "config", "init")
            self.run_cli(base, "-c", config, "config", "check")
            self.assertIn("normal.j2", self.run_cli(base, "template", "list"))

    def test_wechat_runs_with_alipay_physically_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(
                ROOT / "fane",
                base / "fane",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            shutil.rmtree(base / "fane/bill/providers/alipay")
            config, _, _, source = self.fixture(base)
            self.assertEqual(
                json.loads(self.run_cli(base, "providers", "list", "--json")),
                ["wechat"],
            )
            rows = json.loads(
                self.run_cli(
                    base,
                    "-c",
                    config,
                    "convert",
                    "-p",
                    "wechat",
                    "-s",
                    source,
                    "-f",
                    "json",
                )
            )
            self.assertEqual(rows[0]["fingerprint"], "wechat:fixture")

    def test_jsonl_pipeline_preserves_entries_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # Run repository code without the other fixture paths affecting package imports.
            shutil.copytree(
                ROOT / "fane",
                base / "fane",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            config, _, _, source = self.fixture(base)
            rows = self.run_cli(
                base,
                "-c",
                config,
                "convert",
                "-p",
                "wechat",
                "-s",
                source,
                "-f",
                "jsonl",
            )
            journal = base / "journal"
            preview = self.run_cli(base, "ingest", journal, input=rows)
            self.assertEqual(json.loads(preview), json.loads(rows))
            self.assertFalse(journal.exists())
            first = json.loads(
                self.run_cli(base, "ingest", journal, "--write", input=rows)
            )
            second = json.loads(
                self.run_cli(base, "ingest", journal, "--write", input=rows)
            )
            self.assertEqual(first, {"written": 1, "skipped": 0})
            self.assertEqual(second, {"written": 0, "skipped": 1})
            self.assertIn(
                json.loads(rows)["content"], (journal / "2026/2026-01.bean").read_text()
            )

    def test_query_stdin_matches_positional_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(
                ROOT / "fane",
                base / "fane",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            config, _, _, _ = self.fixture(base)
            direct = self.run_cli(
                base, "-c", config, "query", "2026-01-01", "2026-01-31"
            )
            piped = self.run_cli(
                base,
                "-c",
                config,
                "query",
                "-i",
                "-",
                input='{"start_date":"2026-01-01","end_date":"2026-01-31"}',
            )
            self.assertEqual(json.loads(direct), json.loads(piped))
