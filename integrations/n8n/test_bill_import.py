import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fane.bill.providers.wechat.reader import Wechat
from fane.bill.sync import SyncService
from fane.flow.bill import BillFlow
from fane.shared.config import Config, SyncJob
from fane.shared.errors import ProviderError, SyncError
from fane.shared.models import Type


class BillImportTests(unittest.TestCase):
    def test_scan_payment_preserves_direction_amount_and_metadata(self):
        row = {
            "交易时间": "2026-11-08 01:00:00",
            "交易单号": "test-order",
            "商户单号": "test-merchant",
            "收/支": "支出",
            "交易对方": "测试商户",
            "商品": "测试商品",
            "金额(元)": "¥12.34",
            "当前状态": "支付成功",
            "支付方式": "零钱",
            "交易类型": "扫二维码付款",
        }
        reader = Wechat()
        order = reader.convert_orders([reader.parse_order(row)]).orders[0]
        self.assertEqual(order.type, Type.SEND)
        self.assertEqual(str(order.money), "12.34")
        self.assertEqual(order.meta_data["tx_type"], "扫二维码付款")
        row["交易类型"] = "未知新类型"
        with self.assertRaisesRegex(ProviderError, "未知新类型"):
            reader.parse_order(row)

    def test_sync_and_flow_preserve_actual_failed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bill = root / "wechat.xlsx"
            bill.write_bytes(b"fixture")
            job = SyncJob.model_validate(
                {
                    "journal-dir": str(root / "journal"),
                    "state-file": str(root / "state.json"),
                    "lock-file": str(root / "sync.lock"),
                    "dedupe-index": str(root / "imported.jsonl"),
                    "sources": [
                        {"id": "wechat", "provider": "wechat", "path": str(bill)}
                    ],
                }
            )
            config = Config(jobs={"daily": job})
            error = ProviderError("交易类型 包含不支持的值: 未知新类型")
            with patch.object(SyncService, "_compile", side_effect=error):
                with self.assertRaisesRegex(
                    SyncError, "来源 wechat（wechat），文件 wechat.xlsx"
                ):
                    SyncService(config, "daily", job).run(dry_run=True)
                with (
                    patch("fane.flow.bill.unpack", return_value=b"fixture"),
                    patch("fane.flow.bill.load_config_model", return_value=config),
                ):
                    incoming = root / "state/bills/incoming"
                    incoming.mkdir(parents=True)
                    (incoming / "test.zip").write_bytes(b"fixture")
                    result = BillFlow(root, root / "config.yaml").prepare(
                        {
                            "provider": "alipay",
                            "file": "test.zip",
                            "date": "2026-11-08",
                        }
                    )[0]
            self.assertFalse(result["ok"])
            self.assertEqual(result["stage"], "import")
            self.assertIn("来源 wechat（wechat）", result["error"])
            self.assertIn("未知新类型", result["error"])


if __name__ == "__main__":
    unittest.main()
