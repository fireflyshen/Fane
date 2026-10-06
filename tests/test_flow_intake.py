"""n8n intake commands against private temporary fixtures, never real bills."""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from beancount import loader
from openpyxl import Workbook

from fane.flow.bill import BillFlow

ROOT = Path(__file__).resolve().parents[1]


class FlowIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / "data/account"
        self.month = self.ledger / "journal/2026/2026-02.bean"
        self.month.parent.mkdir(parents=True)
        self.month.write_text("")
        accounts = self.ledger / "accounts/data"
        accounts.mkdir(parents=True)
        (accounts / "expenses.bean").write_text(
            "2020-01-01 open Expenses:FIXME CNY\n2020-01-01 open Expenses:Food CNY\n"
        )
        (accounts / "assets.bean").write_text("2020-01-01 open Assets:Cash CNY\n")
        (self.ledger / "main.bean").write_text(
            'option "operating_currency" "CNY"\ninclude "accounts/data/*.bean"\ninclude "journal/2026/2026-02.bean"\n'
        )
        config_dir = self.root / "config"
        config_dir.mkdir()
        self.config = config_dir / "fane.yaml"
        self.config.write_text(
            "default-minus-account: Assets:Cash\ndefault-plus-account: Expenses:FIXME\nledger:\n  file: ../data/account/main.bean\nwechat:\n  rules: []\nalipay:\n  rules: []\njobs:\n  daily:\n    journal-dir: data/account/journal\n    state-file: state/bills/sync.json\n    lock-file: state/bills/sync.lock\n    dedupe-index: state/bills/imported.jsonl\n    sources:\n      - id: alipay\n        provider: alipay\n        path: data/bills/alipay/{date}.csv\n      - id: wechat\n        provider: wechat\n        path: data/bills/wechat/{date}.xlsx\n"
        )
        (config_dir / "subscriptions.json").write_text(
            json.dumps(
                [
                    {
                        "id": "test-sub",
                        "type": "expense",
                        "payee": "Fixture subscription",
                        "narration": "Monthly",
                        "debit_account": "Expenses:Food",
                        "credit_account": "Assets:Cash",
                        "amount": "2.34",
                        "currency": "CNY",
                        "start_date": "2026-02-01",
                        "end_date": "2026-02-28",
                        "billing_day": 5,
                    }
                ]
            )
        )

    def archive(self, provider="wechat"):
        incoming = self.root / "state/bills/incoming/test.zip"
        incoming.parent.mkdir(parents=True, exist_ok=True)
        if provider == "wechat":
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
                    "2026-02-05 12:00:00",
                    "flow-test",
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
            data = io.BytesIO()
            workbook.save(data)
            raw, name = data.getvalue(), "bill.xlsx"
        else:
            raw = "交易时间,交易分类,交易订单号,商家订单号,交易对方,商品说明,对方账号,金额,收/支,交易状态,收/付款方式,备注\n2026-02-05 12:00:00,餐饮,flow-test,merchant,店,午餐,账号,12.34,支出,支付成功,余额,\n".encode()
            name = "bill.csv"
        with zipfile.ZipFile(incoming, "w") as archive:
            archive.writestr(name, raw)
        return {"provider": provider, "file": "test.zip", "date": "2026-02-05"}

    def run_cli(self, operation, *args, payload=None):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fane",
                "-c",
                str(self.config),
                "flow",
                "--root",
                str(self.root),
                "bill",
                operation,
                *args,
            ],
            cwd=ROOT,
            input=json.dumps(payload) if payload else None,
            text=True,
            capture_output=True,
            env={**os.environ, "FANE_STATE_HOME": str(self.root / "state/fane")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_intake_json_contract_fingerprints_and_repeated_import(self):
        for provider in ("alipay", "wechat"):
            with self.subTest(provider=provider):
                meta = self.archive(provider)
                first = self.run_cli("prepare", payload=meta)[0]
                self.assertEqual(set(first), {"ok", "payload", "import", "has_fixme"})
                self.assertTrue(first["ok"])
                self.assertTrue(first["has_fixme"])
                self.assertEqual(first["import"]["written"], 1)
                self.assertEqual(first["payload"]["schema_version"], 1)
                source = (
                    self.root
                    / f"data/bills/{provider}/2026-02-05.{'csv' if provider == 'alipay' else 'xlsx'}"
                )
                self.assertEqual(
                    Path(str(source) + ".md5").read_text().strip(),
                    hashlib.md5(source.read_bytes()).hexdigest(),
                )
                before = self.month.read_bytes()
                meta = self.archive(provider)
                encoded = base64.b64encode(json.dumps(meta).encode()).decode()
                second = self.run_cli("prepare", encoded)[0]
                self.assertTrue(second["ok"])
                self.assertEqual(second["import"]["written"], 0)
                self.assertEqual(before, self.month.read_bytes())
        self.assertEqual(
            len((self.root / "state/bills/imported.jsonl").read_text().splitlines()), 2
        )

    def test_finish_preview_then_write_preserves_subscription_deduplication(self):
        first = self.run_cli("finish", "--preview")
        self.assertTrue(first["ok"])
        self.assertEqual(first["subscriptions"]["written"], 0)
        self.assertEqual(self.month.read_text(), "")
        written = self.run_cli("finish")
        self.assertTrue(written["ok"])
        self.assertEqual(written["subscriptions"]["written"], 1)
        before = self.month.read_bytes()
        self.assertEqual(self.run_cli("finish")["subscriptions"]["total"], 0)
        self.assertEqual(before, self.month.read_bytes())
        self.assertEqual(loader.load_file(str(self.ledger / "main.bean"))[1], [])

    def test_classification_finish_reuses_validation_and_does_not_reimport(self):
        prepared = self.run_cli("prepare", payload=self.archive())[0]
        posting = prepared["payload"]["transactions"][0]["placeholder_postings"][0]
        decision = {
            "schema_version": 1,
            "decisions": [
                {
                    "posting_id": posting["posting_id"],
                    "action": "apply",
                    "replacement_account": "Expenses:Food",
                    "confidence": 0.99,
                    "reason": "Lunch",
                    "new_account": None,
                    "rule": {
                        "provider": "wechat",
                        "account_field": "target-account",
                        "match": {"peer": "店", "item": "午餐"},
                    },
                }
            ],
        }
        encoded = base64.b64encode(json.dumps(decision).encode()).decode()

        # The external Fava validator is simulated; parsing still validates the actual modified ledger.
        def validate(command, cwd, label):
            if command[0] == "docker":
                self.assertEqual(
                    loader.load_file(str(self.ledger / "main.bean"))[1], []
                )
            else:
                result = subprocess.run(command, cwd=cwd, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

        with patch("fane.classify.service._run_command", side_effect=validate):
            result = BillFlow(self.root, self.config).finish({"decisions_b64": encoded})
        self.assertTrue(result["ok"])
        self.assertEqual(result["classification"]["status"], "applied")
        self.assertNotIn("Expenses:FIXME 12.34", self.month.read_text())
        before = self.month.read_bytes()
        again = BillFlow(self.root, self.config).finish({"decisions_b64": encoded})
        self.assertEqual(again, {"ok": False, "stage": "classify"})
        self.assertEqual(before, self.month.read_bytes())

    def test_bad_archive_returns_stage_failure_without_ledger_write(self):
        self.archive()
        (self.root / "state/bills/incoming/test.zip").write_bytes(b"invalid")
        response = self.run_cli(
            "prepare",
            payload={"provider": "wechat", "file": "test.zip", "date": "2026-02-05"},
        )
        self.assertEqual(
            response, [{"ok": False, "stage": "unzip", "provider": "wechat"}]
        )
        self.assertEqual(self.month.read_text(), "")
