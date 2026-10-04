"""Exercise the public CLI against disposable bills and Beancount ledgers."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beancount import loader
from jinja2 import DictLoader, Environment
from openpyxl import Workbook
from typer.main import get_command
from typer.testing import CliRunner

from fane.core.errors import TemplateError
from fane.entrypoints.cli import app
from fane.infrastructure.rendering import templates

ROOT = Path(__file__).resolve().parents[1]


class PublicCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.yaml"
        self.ledger = self.root / "main.bean"
        self.journal = self.root / "journal"
        self.data = self.root / "accounts" / "data"
        self.data.mkdir(parents=True)
        self.month = self.journal / "2026" / "2026-02.bean"
        self.month.parent.mkdir(parents=True)
        self.month.write_text("")
        (self.month.parent / "index.bean").write_text('include "2026-02.bean"\n')
        (self.journal / "index.bean").write_text('include "2026/index.bean"\n')
        (self.data / "expenses.bean").write_text(
            "2020-01-01 open Expenses:FIXME CNY\n"
            "2020-01-01 open Expenses:Food CNY\n"
            "2020-01-01 open Expenses:Subscriptions CNY\n"
        )
        (self.data / "assets.bean").write_text("2020-01-01 open Assets:Cash CNY\n")
        self.ledger.write_text(
            'option "operating_currency" "CNY"\n'
            'include "accounts/data/*.bean"\n'
            'include "journal/index.bean"\n'
            "2020-01-02 balance Expenses:FIXME 0 CNY\n"
            "2020-01-02 balance Expenses:Food 0 CNY\n"
            "2020-01-02 balance Expenses:Subscriptions 0 CNY\n"
        )
        self.config.write_text(
            "default-minus-account: Assets:Cash\n"
            "default-plus-account: Expenses:FIXME\n"
            "default-currency: CNY\n"
            "alipay:\n  rules: []\n"
            "wechat:\n  rules: []\n"
            "ledger:\n  file: main.bean\n"
        )
        self.env = dict(os.environ)
        for name in (
            "FANE_CONFIG",
            "FANE_LEDGER",
            "BILLS_LEDGER",
            "BILLS_ROOT",
            "FANE_STATE_NAMESPACE",
        ):
            self.env.pop(name, None)
        self.env["FANE_STATE_HOME"] = str(self.root / "state")

    def run_cli(self, *args, input=None):
        return subprocess.run(
            [sys.executable, "-m", "fane", "--config", str(self.config), *args],
            cwd=ROOT,
            env=self.env,
            input=input,
            capture_output=True,
            text=True,
        )

    def success(self, *args, input=None):
        result = self.run_cli(*args, input=input)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def bill(self):
        source = self.root / "wechat.xlsx"
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
                "test-cli-v2",
                "/",
                "支出",
                "咖啡店",
                "午餐",
                "10.00",
                "支付成功",
                "零钱",
                "商户消费",
            ]
        )
        workbook.save(source)
        return ["--provider", "wechat", "--source", str(source)]

    def plan(self):
        plan = self.root / "subscriptions.json"
        plan.write_text(
            json.dumps(
                [
                    {
                        "id": "test-service",
                        "status": "active",
                        "type": "expense",
                        "interval": "monthly",
                        "payee": '服务 "A"',
                        "narration": "月度订阅",
                        "debit_account": "Expenses:Subscriptions",
                        "credit_account": "Assets:Cash",
                        "amount": "10.00",
                        "currency": "CNY",
                        "billing_day": 31,
                        "start_date": "2026-01-01",
                        "end_date": None,
                    }
                ],
                ensure_ascii=False,
            )
        )
        return plan

    def snapshot(self):
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def decision(self):
        self.month.write_text(
            '2026-02-05 * "咖啡店" "午餐"\n'
            '  source: "WeChat"\n'
            '  method: "零钱"\n'
            "  Expenses:FIXME 10.00 CNY\n"
            "  Assets:Cash -10.00 CNY\n"
        )
        extracted = json.loads(self.success("classify", "extract"))
        posting = extracted["transactions"][0]["placeholder_postings"][0]
        return json.dumps(
            {
                "schema_version": 1,
                "decisions": [
                    {
                        "posting_id": posting["posting_id"],
                        "action": "apply",
                        "replacement_account": "Expenses:Food",
                        "confidence": 0.99,
                        "reason": "午餐属于餐饮支出",
                        "new_account": None,
                        "rule": {
                            "provider": "wechat",
                            "account_field": "target-account",
                            "match": {"peer": "咖啡店", "item": "午餐"},
                        },
                    }
                ],
            },
            ensure_ascii=False,
        )

    def test_every_public_command_help_works_without_config(self):
        runner = CliRunner()
        leaves = []

        def visit(command, path=()):
            if hasattr(command, "commands"):
                for name, child in command.commands.items():
                    if not child.hidden:
                        visit(child, (*path, name))
            else:
                leaves.append(path)

        visit(get_command(app))
        self.assertEqual(len(leaves), 23)
        reference = (ROOT / "docs" / "COMMANDS.md").read_text()
        registered = get_command(app)
        for path in leaves:
            with self.subTest(command=path):
                heading = "## fa " + " ".join(path)
                self.assertIn(heading + "\n", reference)
                section = reference.split(heading + "\n", 1)[1].split("\n## ", 1)[0]
                command = registered
                for name in path:
                    command = command.commands[name]
                for parameter in command.params:
                    if not getattr(parameter, "hidden", False):
                        for option in parameter.opts:
                            self.assertIn(option, section)
                result = runner.invoke(
                    app, ["--config", str(self.root / "missing.yaml"), *path, "--help"]
                )
                self.assertEqual(result.exit_code, 0, result.output)

    def test_catalogs_and_schema_without_config(self):
        self.config.unlink()
        self.assertEqual(
            json.loads(self.success("providers", "list", "--json")),
            ["alipay", "wechat"],
        )
        self.assertIn(
            "normal.j2", json.loads(self.success("template", "list", "--json"))
        )
        self.assertEqual(
            json.loads(self.success("classify", "schema"))["properties"][
                "schema_version"
            ]["const"],
            1,
        )
        self.assertIn(
            "money",
            {
                r["name"]
                for r in json.loads(self.success("template", "fields", "--json"))
            },
        )

    def test_conversion_formats_and_custom_template(self):
        flags = self.bill()
        text = self.success("bill", "convert", *flags)
        self.assertIn("Expenses:FIXME", text)
        rows = json.loads(self.success("bill", "convert", *flags, "--format", "json"))
        self.assertEqual(rows[0]["fingerprint"], "wechat:test-cli-v2")
        self.assertEqual(
            json.loads(self.success("bill", "convert", *flags, "--format", "jsonl")),
            rows[0],
        )
        legacy = json.loads(
            self.success("bill", "convert", *flags, "--format", "legacy-json")
        )
        self.assertIn("02", legacy["expense"])
        template = self.root / "custom.j2"
        self.success("template", "show", "--output", str(template))
        template.write_text("; 自定义模板\n" + template.read_text())
        self.success("template", "check", "--file", str(template))
        custom = self.success("bill", "convert", *flags, "--template", str(template))
        self.assertIn("; 自定义模板", custom)
        self.config.write_text(self.config.read_text() + "template-file: custom.j2\n")
        self.assertIn("; 自定义模板", self.success("bill", "convert", *flags))

    def test_import_preview_dedupe_and_explicit_write(self):
        flags = [*self.bill(), "--journal-dir", str(self.journal)]
        before = self.snapshot()
        self.assertEqual(
            json.loads(self.success("bill", "import", *flags))["fingerprint"],
            "wechat:test-cli-v2",
        )
        self.assertEqual(self.snapshot(), before)
        written = json.loads(self.success("bill", "import", *flags, "--write"))
        self.assertEqual(written, {"written": 1, "skipped": 0})
        self.assertEqual(self.success("bill", "import", *flags), "")
        self.assertEqual(
            json.loads(self.success("bill", "import", *flags, "--write")),
            {"written": 0, "skipped": 1},
        )

    def test_unclassified_import_rejected_without_changes(self):
        flags = [
            *self.bill(),
            "--journal-dir",
            str(self.journal),
            "--require-classified",
            "--write",
        ]
        before = self.snapshot()
        self.assertNotEqual(self.run_cli("bill", "import", *flags).returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_sync_preview_reports_zero_written_then_write_is_incremental(self):
        self.bill()
        self.config.write_text(
            self.config.read_text()
            + f"jobs:\n  daily:\n    journal-dir: {self.journal}\n    sources:\n      - id: wechat\n        provider: wechat\n        path: {self.root / 'wechat.xlsx'}\n"
        )
        self.assertEqual(json.loads(self.success("bill", "jobs", "--json")), ["daily"])
        preview = json.loads(self.success("bill", "sync", "daily", "--json"))
        self.assertEqual((preview["planned"], preview["written"]), (1, 0))
        self.assertEqual(self.month.read_text(), "")
        self.assertEqual(
            json.loads(self.success("bill", "sync", "daily", "--json", "--write"))[
                "written"
            ],
            1,
        )
        self.assertEqual(
            json.loads(self.success("bill", "sync", "daily", "--json", "--write"))[
                "status"
            ],
            "noop",
        )

    def test_classification_preview_write_and_rule_on_future_bill(self):
        decision = self.decision()
        before = self.snapshot()
        self.assertEqual(
            json.loads(self.success("classify", "apply", input=decision))["status"],
            "dry-run",
        )
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            json.loads(self.success("classify", "apply", "--write", input=decision))[
                "status"
            ],
            "applied",
        )
        self.assertNotIn("Expenses:FIXME 10", self.month.read_text())
        self.success("config", "check", "--strict")
        self.success("ledger", "validate")
        self.assertIn("Expenses:Food", self.success("bill", "convert", *self.bill()))

    def test_classification_failed_validator_rolls_back_all_files(self):
        decision = self.decision()
        before = self.snapshot()
        validator = shlex.join([sys.executable, "-c", "raise SystemExit(9)"])
        result = self.run_cli(
            "classify", "apply", "--write", "--validator", validator, input=decision
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("9", result.stderr)

    def test_classification_creates_expense_account_and_metadata(self):
        payload = json.loads(self.decision())
        decision = payload["decisions"][0]
        decision["replacement_account"] = "Expenses:Dining"
        decision["new_account"] = {"comment_zh": "餐饮支出", "flux_label": "餐饮"}
        self.success("classify", "apply", "--write", input=json.dumps(payload))
        text = (self.data / "expenses.bean").read_text()
        self.assertIn("2026-02-05 open Expenses:Dining", text)
        self.assertIn('flux_label: "餐饮"', text)
        self.success("ledger", "validate")

    def test_custom_template_unknown_variable_reports_clear_error(self):
        flags = self.bill()
        template = self.root / "unknown.j2"
        template.write_text("{{ missing_field }}")
        self.success("template", "check", "--file", str(template))
        result = self.run_cli("bill", "convert", *flags, "--template", str(template))
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing_field", result.stderr)
        self.assertIn("fa template fields", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_classification_stale_decision_rejected(self):
        decision = self.decision()
        self.month.write_text(self.month.read_text().replace("10.00", "11.00"))
        before = self.snapshot()
        result = self.run_cli("classify", "apply", "--write", input=decision)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.snapshot(), before)

    def test_subscriptions_month_end_escaping_and_idempotence(self):
        self.plan()
        self.success("subscriptions", "check", "--json")
        before = self.snapshot()
        preview = json.loads(
            self.success("subscriptions", "generate", "--month", "2026-02", "--json")
        )
        self.assertEqual(preview["entries"][0]["date"], "2026-02-28")
        self.assertEqual(preview["written"], 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            json.loads(
                self.success(
                    "subscriptions",
                    "generate",
                    "--month",
                    "2026-02",
                    "--json",
                    "--write",
                )
            )["written"],
            1,
        )
        entries, errors, _ = loader.load_file(str(self.ledger))
        self.assertEqual(errors, [])
        self.assertTrue(any(getattr(e, "payee", None) == '服务 "A"' for e in entries))
        self.assertEqual(
            json.loads(
                self.success(
                    "subscriptions",
                    "generate",
                    "--month",
                    "2026-02",
                    "--json",
                    "--write",
                )
            )["total"],
            0,
        )

    def test_subscription_unincluded_output_rolls_back(self):
        self.plan()
        self.ledger.write_text(
            self.ledger.read_text().replace('include "journal/index.bean"\n', "")
        )
        before = self.snapshot()
        result = self.run_cli(
            "subscriptions", "generate", "--month", "2026-03", "--write"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未被主账本引用", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_init_duplicate_and_invalid_subscription_parameters(self):
        self.success("subscriptions", "init")
        self.assertNotEqual(self.run_cli("subscriptions", "init").returncode, 0)
        self.assertEqual(
            json.loads((self.root / "subscriptions.json").read_text())[0]["status"],
            "paused",
        )
        self.assertNotEqual(
            self.run_cli(
                "subscriptions",
                "generate",
                "--month",
                "2026-02",
                "--until",
                "2026-02-28",
            ).returncode,
            0,
        )
        plan = self.plan()
        payload = json.loads(plan.read_text())
        payload[0]["amount"] = "NaN"
        plan.write_text(json.dumps(payload))
        self.assertNotEqual(self.run_cli("subscriptions", "check").returncode, 0)

    def test_missing_template_and_syntax_errors_are_actionable(self):
        result = self.run_cli(
            "template", "check", "--file", str(self.root / "missing.j2")
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("模板文件不存在", result.stderr)
        broken = self.root / "broken.j2"
        broken.write_text("{% if %}")
        self.assertIn(
            "模板语法错误",
            self.run_cli("template", "check", "--file", str(broken)).stderr,
        )
        self.config.write_text(self.config.read_text() + "template-file: missing.j2\n")
        self.assertEqual(self.run_cli("config", "check", "--json").returncode, 1)
        with patch.object(templates, "env", Environment(loader=DictLoader({}))):
            with self.assertRaisesRegex(TemplateError, "重新安装"):
                templates.get_template()


if __name__ == "__main__":
    unittest.main()
