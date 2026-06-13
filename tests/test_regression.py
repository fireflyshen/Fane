import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ir.ir import Order, Type
from package.config import Config, init_config
from package.errors import ConfigError, ProviderError
from package.parser.ali.alipay import AlipayAnalyser
from package.parser.wechat.wechat import WechatAnalyser
from provider.ali.alipay import AliPay

ROOT = Path(__file__).resolve().parents[1]


class CliRegressionTest(unittest.TestCase):
    def run_trans(self, provider: str, source: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--config",
                "example/config.yaml",
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

    def test_alipay_example_output_shape_is_stable(self):
        data = self.run_trans("alipay", "example/2.csv")

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

    def test_wechat_example_output_shape_is_stable(self):
        data = self.run_trans("wechat", "example/3.xlsx")

        self.assertEqual(sorted(data.keys()), ["expense", "income"])
        self.assertEqual(sorted(data["expense"].keys()), ["04"])
        self.assertEqual(data["income"], {})
        self.assertEqual(len(data["expense"]["04"]), 1)
        self.assertIn("顺丰速运", data["expense"]["04"][0])
        self.assertIn("Expenses:Life:Logistics", data["expense"]["04"][0])

    def test_missing_source_exits_with_clear_error(self):
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


class RuleRegressionTest(unittest.TestCase):
    def test_alipay_refund_keeps_existing_account_swap_behavior(self):
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


class RobustnessTest(unittest.TestCase):
    def test_empty_config_file_has_clear_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml") as config_file:
            with self.assertRaisesRegex(ConfigError, "配置文件为空"):
                init_config(config_file.name)

    def test_alipay_missing_required_columns_has_clear_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv") as bill_file:
            bill_file.write("交易时间,交易分类\n2026-01-01 00:00:00,测试\n")
            bill_file.flush()

            with self.assertRaisesRegex(ProviderError, "账单文件缺少必要列"):
                AliPay().translate(bill_file.name)

    def test_alipay_unknown_status_has_clear_error(self):
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

    def test_wechat_rule_match_keeps_account_resolution_behavior(self):
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
