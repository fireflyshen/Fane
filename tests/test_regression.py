import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ir.ir import IR, Order, Type
from package.config import Config, init_config, load_config
from package.errors import ConfigError, ProviderError
from package.parser.ali.alipay import AlipayAnalyser
from package.parser.wechat.wechat import WechatAnalyser
from provider.ali.alipay import AliPay
from provider.ali.ali_types import DealStatus
from provider.ali.processor import post_process, read_account_balance

ROOT = Path(__file__).resolve().parents[1]


class CliRegressionTest(unittest.TestCase):
    def run_trans(
        self, provider: str, source: str, config: str = "example/config.yaml"
    ) -> dict[str, Any]:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--config",
                config,
                "trans",
                "--provider",
                provider,
                "--source",
                source,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def run_trans_without_foreign_repayments(
        self, provider: str, source: str
    ) -> dict[str, Any]:
        config = load_config(ROOT / "example/config.yaml")
        config.pop("foreign-credit-card-repayments", None)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", encoding="utf-8"
        ) as config_file:
            json.dump(config, config_file, ensure_ascii=False)
            config_file.flush()
            return self.run_trans(provider, source, config_file.name)

    def test_alipay_example_output_shape_is_stable(self) -> None:
        data = self.run_trans_without_foreign_repayments("alipay", "example/2.csv")

        self.assertEqual(sorted(data.keys()), ["expense", "income"])
        self.assertEqual(sorted(data["expense"].keys()), ["05"])
        self.assertEqual(sorted(data["income"].keys()), ["05"])
        self.assertEqual(len(data["expense"]["05"]), 10)
        self.assertEqual(len(data["income"]["05"]), 8)
        self.assertTrue(
            any(
                "退款-话费自动充值" in item
                and "Assets:FIXME" in item
                and "Expenses:Utilities:Phone" in item
                for item in data["expense"]["05"]
            )
        )

    def test_wechat_example_output_shape_is_stable(self) -> None:
        data = self.run_trans_without_foreign_repayments("wechat", "example/3.xlsx")

        self.assertEqual(sorted(data.keys()), ["expense", "income"])
        self.assertEqual(sorted(data["expense"].keys()), ["04"])
        self.assertEqual(data["income"], {})
        self.assertEqual(len(data["expense"]["04"]), 1)
        self.assertIn("顺丰速运", data["expense"]["04"][0])
        self.assertIn("Expenses:Life:Logistics", data["expense"]["04"][0])

    def test_missing_source_exits_with_clear_error(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--config",
                "example/config.yaml",
                "trans",
                "--provider",
                "alipay",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("请通过 --source/-s 指定账单文件", result.stderr)

    def test_trans_jsonl_format_outputs_structured_entries(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--config",
                "example/config.yaml",
                "trans",
                "--provider",
                "wechat",
                "--source",
                "example/3.xlsx",
                "--format",
                "jsonl",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        rows = [json.loads(line) for line in result.stdout.splitlines() if line]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "expense")
        self.assertEqual(rows[0]["month"], "04")
        self.assertIn("顺丰速运", rows[0]["content"])
        self.assertTrue(rows[0]["fingerprint"].startswith("wechat:"))

    def test_trans_beancount_format_outputs_plain_entries(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--config",
                "example/config.yaml",
                "trans",
                "--provider",
                "wechat",
                "--source",
                "example/3.xlsx",
                "--format",
                "beancount",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("2026-04", result.stdout)
        self.assertIn("顺丰速运", result.stdout)
        self.assertNotIn('"expense"', result.stdout)

    def test_import_command_writes_entries_once_by_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as journal_dir:
            dedupe_index = str(Path(journal_dir) / ".fane" / "imported.jsonl")
            first = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--config",
                    "example/config.yaml",
                    "import",
                    "--provider",
                    "wechat",
                    "--source",
                    "example/3.xlsx",
                    "--journal-dir",
                    journal_dir,
                    "--dedupe-index",
                    dedupe_index,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--config",
                    "example/config.yaml",
                    "import",
                    "--provider",
                    "wechat",
                    "--source",
                    "example/3.xlsx",
                    "--journal-dir",
                    journal_dir,
                    "--dedupe-index",
                    dedupe_index,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            first_result = json.loads(first.stdout)
            second_result = json.loads(second.stdout)
            target_file = Path(journal_dir) / "2026" / "2026-04.bean"

            self.assertEqual(first_result, {"written": 1, "skipped": 0})
            self.assertEqual(second_result, {"written": 0, "skipped": 1})
            self.assertIn("顺丰速运", target_file.read_text(encoding="utf-8"))


class RuleRegressionTest(unittest.TestCase):
    def test_alipay_refund_keeps_existing_account_swap_behavior(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "alipay": {
                    "rules": [
                        {
                            "peer": "中国移动",
                            "target-account": "Expenses:Utilities:Phone",
                        },
                        {
                            "method": "工商银行信用卡(8393)",
                            "method-account": "Liabilities:CreditCard:ICBC-8393",
                        },
                    ]
                },
            }
        )
        order = Order(
            peer="中国移动",
            item="退款-话费自动充值",
            method="工商银行信用卡(8393)",
            type=Type.UNKNOW,
        )

        result = AlipayAnalyser().get_account_and_tags(order, cfg)

        self.assertEqual(
            result,
            (
                False,
                "Expenses:Utilities:Phone",
                "Assets:FIXME",
                {},
                [],
            ),
        )

    def test_alipay_rule_can_match_amount_and_timestamp_range(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "alipay": {
                    "rules": [
                        {
                            "method": "工商银行信用卡(8393)",
                            "method-account": "Liabilities:CreditCard:ICBC-8393",
                        },
                        {
                            "timestamp-range": "2026-06-01..2026-06-30",
                            "min-price": "100.00",
                            "max-price": "200.00",
                            "target-account": "Expenses:Food:Groceries",
                        },
                    ]
                },
            }
        )
        order = Order(
            peer="测试商户",
            item="测试消费",
            method="工商银行信用卡(8393)",
            money=Decimal("150.00"),
            pay_time=datetime(2026, 6, 14, 12, 30, 0),
            type=Type.SEND,
        )

        result = AlipayAnalyser().get_account_and_tags(order, cfg)

        self.assertEqual(
            result,
            (
                False,
                "Liabilities:CreditCard:ICBC-8393",
                "Expenses:Food:Groceries",
                {},
                [],
            ),
        )

    def test_alipay_amount_range_does_not_match_outside_amount(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "alipay": {
                    "rules": [
                        {
                            "method": "工商银行信用卡(8393)",
                            "method-account": "Liabilities:CreditCard:ICBC-8393",
                        },
                        {
                            "timestamp-range": "2026-06-01..2026-06-30",
                            "min-price": "100.00",
                            "max-price": "200.00",
                            "target-account": "Expenses:Food:Groceries",
                        },
                    ]
                },
            }
        )
        order = Order(
            peer="测试商户",
            item="测试消费",
            method="工商银行信用卡(8393)",
            money=Decimal("250.00"),
            pay_time=datetime(2026, 6, 14, 12, 30, 0),
            type=Type.SEND,
        )

        result = AlipayAnalyser().get_account_and_tags(order, cfg)

        self.assertEqual(
            result,
            (
                False,
                "Liabilities:CreditCard:ICBC-8393",
                "Expenses:FIXME",
                {},
                [],
            ),
        )

    def test_alipay_rule_can_match_monthly_day_range(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "alipay": {
                    "rules": [
                        {
                            "day-range": "15-16",
                            "min-amount": "100.00",
                            "max-amount": "200.00",
                            "target-account": "Expenses:Monthly:MidMonth",
                        }
                    ]
                },
            }
        )
        matching_order = Order(
            peer="测试商户",
            item="月中消费",
            money=Decimal("150.00"),
            pay_time=datetime(2026, 7, 15, 12, 30, 0),
            type=Type.SEND,
        )
        outside_order = Order(
            peer="测试商户",
            item="月中消费",
            money=Decimal("150.00"),
            pay_time=datetime(2026, 7, 17, 12, 30, 0),
            type=Type.SEND,
        )

        matching_result = AlipayAnalyser().get_account_and_tags(matching_order, cfg)
        outside_result = AlipayAnalyser().get_account_and_tags(outside_order, cfg)

        self.assertEqual(
            matching_result,
            (
                False,
                "Assets:FIXME",
                "Expenses:Monthly:MidMonth",
                {},
                [],
            ),
        )
        self.assertEqual(
            outside_result,
            (
                False,
                "Assets:FIXME",
                "Expenses:FIXME",
                {},
                [],
            ),
        )

    def test_wechat_rule_can_match_clock_time_and_amount_range(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "wechat": {
                    "rules": [
                        {
                            "time": "08:00..09:00",
                            "min-amount": "7.00",
                            "max-amount": "8.00",
                            "target-account": "Expenses:Transport:Bus",
                        }
                    ]
                },
            }
        )
        order = Order(
            peer="南阳市公共交通集团有限责任公司",
            item="公交乘车",
            money=Decimal("7.00"),
            pay_time=datetime(2026, 6, 14, 8, 30, 0),
            type=Type.SEND,
        )

        result = WechatAnalyser().get_account_and_tags(order, cfg)

        self.assertEqual(
            result,
            (
                False,
                "Assets:FIXME",
                "Expenses:Transport:Bus",
                {},
                [],
            ),
        )


class AlipayPostProcessRegressionTest(unittest.TestCase):
    def test_post_process_does_not_generate_repay_order_from_note(self) -> None:
        order = Order(
            peer="信用卡还款",
            note="icbc_usd;10;72 usd",
            meta_data={"status": DealStatus.SUCCESS.value},
        )

        result = post_process(IR(orders=[order]))

        self.assertEqual(result.orders, [order])

    def test_post_process_does_not_generate_google_order(self) -> None:
        result = post_process(IR(orders=[]))

        self.assertEqual(result.orders, [])

    def test_post_process_keeps_status_filters(self) -> None:
        closed_order = Order(
            peer="关闭交易",
            meta_data={"status": DealStatus.CLOSE.value, "type": "不计收支"},
        )
        pending_order = Order(
            peer="等待确认收货",
            meta_data={"status": DealStatus.SHOP_PENDING.value},
        )
        success_order = Order(
            peer="正常交易",
            meta_data={"status": DealStatus.SUCCESS.value},
        )

        result = post_process(IR(orders=[closed_order, pending_order, success_order]))

        self.assertEqual(result.orders, [success_order])

    def test_post_process_adds_foreign_card_repayment_after_4931_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as ledger_dir:
            ledger_path = Path(ledger_dir) / "main.bean"
            journal_path = Path(ledger_dir) / "journal.bean"
            ledger_path.write_text('include "./journal.bean"\n', encoding="utf-8")
            journal_path.write_text(
                '2026-06-01 * "OpenAI" "API"\n'
                "  Expenses:Tech:AI                         123.45 USD\n"
                "  Liabilities:CreditCard:ICBC-USD         -123.45 USD\n",
                encoding="utf-8",
            )

            cfg = Config.model_validate(
                {
                    "default-minus-account": "Assets:FIXME",
                    "default-plus-account": "Expenses:FIXME",
                    "foreign-credit-card-repayments": [
                        {
                            "trigger-minus-account": "Assets:MMF:Alipay:YuEBao",
                            "trigger-plus-account": "Assets:DebitCard:ICBC:4931",
                            "liability-account": "Liabilities:CreditCard:ICBC-USD",
                            "ledger-file": str(ledger_path),
                            "currency": "USD",
                            "peer": "中国工商银行",
                            "item": "外币信用卡还款",
                        }
                    ],
                }
            )
            order = Order(
                peer="中国工商银行",
                item="余额宝-转出到银行卡",
                money=Decimal("895.20"),
                minus_account="Assets:MMF:Alipay:YuEBao",
                plus_account="Assets:DebitCard:ICBC:4931",
                meta_data={"status": DealStatus.SUCCESS.value},
            )

            result = post_process(IR(orders=[order]), cfg)

        self.assertEqual(len(result.orders), 2)
        self.assertIs(result.orders[0], order)
        self.assertEqual(result.orders[0].plus_account, "Assets:DebitCard:ICBC:4931")
        self.assertEqual(result.orders[1].peer, "中国工商银行")
        self.assertEqual(result.orders[1].item, "外币信用卡还款")
        self.assertEqual(
            result.orders[1].plus_account, "Liabilities:CreditCard:ICBC-USD"
        )
        self.assertEqual(result.orders[1].minus_account, "Assets:DebitCard:ICBC:4931")
        self.assertEqual(result.orders[1].plus_str, "123.45 USD @@ 895.20 CNY")
        self.assertEqual(result.orders[1].minus_str, "-895.20 CNY")

    def test_foreign_card_balance_includes_balance_directive(self) -> None:
        with tempfile.TemporaryDirectory() as ledger_dir:
            ledger_path = Path(ledger_dir) / "main.bean"
            init_path = Path(ledger_dir) / "init.bean"
            journal_path = Path(ledger_dir) / "journal.bean"
            ledger_path.write_text(
                'include "./init.bean"\ninclude "./journal.bean"\n',
                encoding="utf-8",
            )
            init_path.write_text(
                "2025-11-19 pad Liabilities:CreditCard:ICBC-5788 "
                "Equity:Opening-Balances\n"
                "2025-11-20 balance Liabilities:CreditCard:ICBC-5788 "
                "-19.99 USD\n",
                encoding="utf-8",
            )
            journal_path.write_text(
                '2026-06-01 * "Apple" "Gift Card"\n'
                "  Assets:Digital:AppleID                    25.00 USD\n"
                "  Liabilities:CreditCard:ICBC-5788         -25.00 USD\n"
                '2026-06-12 * "ICBC" "Rebate"\n'
                "  Liabilities:CreditCard:ICBC-5788           0.72 USD\n"
                "  Income:Rebates                            -0.72 USD\n",
                encoding="utf-8",
            )

            balance = read_account_balance(
                str(ledger_path), "Liabilities:CreditCard:ICBC-5788", "USD"
            )

        self.assertEqual(balance, Decimal("-44.27"))


class RobustnessTest(unittest.TestCase):
    def test_empty_config_file_has_clear_error(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml") as config_file:
            with self.assertRaisesRegex(ConfigError, "配置文件为空"):
                init_config(config_file.name)

    def test_alipay_missing_required_columns_has_clear_error(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as bill_file:
            bill_file.write("交易时间,交易分类\n2026-01-01 00:00:00,测试\n")
            bill_file.flush()

            with self.assertRaisesRegex(ProviderError, "账单文件缺少必要列"):
                AliPay().translate(bill_file.name)

    def test_alipay_unknown_status_has_clear_error(self) -> None:
        content = (
            "交易时间,交易分类,交易订单号,商家订单号,交易对方,商品说明,对方账号,"
            "金额,收/支,交易状态,收/付款方式,备注\n"
            "2026-01-01 00:00:00,测试,1,2,对方,商品,账号,1.00,支出,未知状态,余额,\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as bill_file:
            bill_file.write(content)
            bill_file.flush()

            with self.assertRaisesRegex(ProviderError, "交易状态 包含不支持的值"):
                AliPay().translate(bill_file.name)

    def test_wechat_rule_match_keeps_account_resolution_behavior(self) -> None:
        cfg = Config.model_validate(
            {
                "default-minus-account": "Assets:FIXME",
                "default-plus-account": "Expenses:FIXME",
                "wechat": {
                    "rules": [
                        {
                            "peer": "顺丰速运",
                            "target-account": "Expenses:Life:Logistics",
                        },
                        {
                            "method": "工商银行信用卡(8393)",
                            "method-account": "Liabilities:CreditCard:ICBC-8393",
                        },
                    ]
                },
            }
        )
        order = Order(
            peer="顺丰速运",
            item="散单运费-顺丰速运",
            method="工商银行信用卡(8393)",
            tx_type_original="商户消费",
            type=Type.SEND,
        )

        result = WechatAnalyser().get_account_and_tags(order, cfg)

        self.assertEqual(
            result,
            (
                False,
                "Liabilities:CreditCard:ICBC-8393",
                "Expenses:Life:Logistics",
                {},
                [],
            ),
        )


if __name__ == "__main__":
    unittest.main()
