import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from ir.ir import IR, Order, Type
from package.compiler.compiler import Compiler
from package.config import Config
from package.parser.ali.alipay import AlipayAnalyser
from package.strategy.template.normal import NormalStrategy


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "main.py", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliToolTest(unittest.TestCase):
    def test_subcommand_help_does_not_require_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.yaml")
            result = run_cli("--config", missing, "trans", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--provider", result.stdout)
        self.assertNotIn("配置出错", result.stderr)

    def test_version_works_from_source_checkout(self) -> None:
        result = run_cli("--version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"Fane Version: \d+\.\d+\.\d+")

    def test_init_and_doctor_work_before_config_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "nested" / "config.yaml"
            initialized = run_cli("--config", str(config), "init")
            diagnosed = run_cli("--config", str(config), "doctor")
            duplicate = run_cli("--config", str(config), "init")

        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertTrue(config.parent.name == "nested")
        self.assertEqual(diagnosed.returncode, 0, diagnosed.stderr)
        self.assertIn("0 个错误", diagnosed.stdout)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("未覆盖", duplicate.stderr)

    def test_doctor_warns_about_unknown_fields_without_breaking_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text(
                "default-minus-account: Assets:FIXME\n"
                "default-plus-account: Expenses:FIXME\n"
                "default-currency: CNY\n"
                "legacy-custom-field: true\n",
                encoding="utf-8",
            )
            compatible = run_cli("--config", str(config), "doctor")
            strict = run_cli("--config", str(config), "doctor", "--strict")

        self.assertEqual(compatible.returncode, 0, compatible.stderr)
        self.assertIn("未识别字段", compatible.stdout)
        self.assertNotEqual(strict.returncode, 0)

    def test_versioned_wechat_fixture_translates_and_imports_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat.xlsx"
            config = root / "config.yaml"
            journal = root / "journal"
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
                    "2026-08-02 12:00:00",
                    "fixture-order-id",
                    "/",
                    "支出",
                    "测试商户",
                    "测试商品",
                    "12.34",
                    "支付成功",
                    "零钱",
                    "商户消费",
                ]
            )
            workbook.save(source)
            config.write_text(
                "default-minus-account: Assets:FIXME\n"
                "default-plus-account: Expenses:FIXME\n"
                "default-currency: CNY\n"
                "wechat:\n"
                "  rules:\n"
                "    - peer: 测试商户\n"
                "      target-account: Expenses:Test\n"
                "    - method: 零钱\n"
                "      method-account: Assets:Cash:WeChat\n",
                encoding="utf-8",
            )

            translated = run_cli(
                "--config",
                str(config),
                "trans",
                "--provider",
                "wechat",
                "--source",
                str(source),
                "--format",
                "jsonl",
            )
            first_import = run_cli(
                "--config",
                str(config),
                "import",
                "--provider",
                "wechat",
                "--source",
                str(source),
                "--journal-dir",
                str(journal),
                "--require-classified",
            )
            second_import = run_cli(
                "--config",
                str(config),
                "import",
                "--provider",
                "wechat",
                "--source",
                str(source),
                "--journal-dir",
                str(journal),
                "--require-classified",
            )

            row = json.loads(translated.stdout)
            target = journal / "2026" / "2026-08.bean"
            imported_text = target.read_text(encoding="utf-8")

        self.assertEqual(translated.returncode, 0, translated.stderr)
        self.assertEqual(row["fingerprint"], "wechat:fixture-order-id")
        self.assertIn("Expenses:Test", row["content"])
        self.assertEqual(json.loads(first_import.stdout), {"written": 1, "skipped": 0})
        self.assertEqual(json.loads(second_import.stdout), {"written": 0, "skipped": 1})
        self.assertIn("Assets:Cash:WeChat", imported_text)


class CompilerReuseTest(unittest.TestCase):
    def test_repeated_build_does_not_duplicate_entries(self) -> None:
        config = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "default-currency": "CNY",
            }
        )
        order = Order(
            pay_time=datetime(2026, 8, 2, 12, 0, 0),
            peer="测试商户",
            item="测试消费",
            money=Decimal("12.34"),
            method="余额",
            type=Type.SEND,
        )
        compiler = Compiler(
            "alipay",
            config,
            IR(orders=[order]),
            NormalStrategy(),
            AlipayAnalyser(),
        )

        first = compiler.build_result()
        second = compiler.build_result()

        self.assertEqual(first, second)
        self.assertEqual(len(second["expense"]["08"]), 1)


if __name__ == "__main__":
    unittest.main()
