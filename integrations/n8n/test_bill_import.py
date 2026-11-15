import base64
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fane.bill.providers.wechat.reader import Wechat
from fane.bill.sync import SyncService
from fane.flow.bill import BillFlow
from fane.shared.config import Config, SyncJob
from fane.shared.errors import ProviderError, SyncError
from fane.shared.models import Type
from fane.shared.results import RenderedEntry


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
        row["交易类型"] = "二维码收款"
        row["收/支"] = "收入"
        receipt = reader.convert_orders([reader.parse_order(row)]).orders[0]
        self.assertEqual(receipt.type, Type.RECV)
        self.assertEqual(receipt.meta_data["tx_type"], "二维码收款")
        row["交易类型"] = "未知新类型"
        unknown = reader.convert_orders([reader.parse_order(row)]).orders[0]
        self.assertEqual(unknown.type, Type.RECV)
        self.assertEqual(unknown.meta_data["tx_type"], "未知新类型")
        row["收/支"] = "未知方向"
        with self.assertRaisesRegex(ProviderError, "未知方向"):
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
                        {
                            "id": "wechat",
                            "provider": "wechat",
                            "path": str(bill),
                        }
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
                    patch(
                        "fane.flow.bill.load_config_model", return_value=config
                    ),
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

    def test_failed_import_recovers_saved_zip_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "state/bills/incoming"
            incoming.mkdir(parents=True)
            (incoming / "mail.zip").write_bytes(b"original zip")
            config = Config(
                jobs={
                    "daily": SyncJob.model_validate(
                        {
                            "journal-dir": "data/account/journal",
                            "state-file": "state/sync.json",
                            "lock-file": "state/sync.lock",
                            "dedupe-index": "state/imported.jsonl",
                            "sources": [
                                {
                                    "id": "wechat",
                                    "provider": "wechat",
                                    "path": "data/bills/wechat/{date}.xlsx",
                                }
                            ],
                        }
                    )
                }
            )
            flow = BillFlow(root, root / "config.yaml")
            meta = {
                "provider": "wechat",
                "file": "mail.zip",
                "date": "2026-11-08",
            }
            entry = RenderedEntry(
                date(2026, 11, 8),
                "11",
                "expense",
                "wechat:test",
                '2026-11-08 * "Test" "Test"\n',
                "wechat",
                "fixture",
                "test",
            )
            with (
                patch("fane.flow.bill.unpack", return_value=b"spreadsheet"),
                patch("fane.flow.bill.load_config_model", return_value=config),
                patch(
                    "fane.flow.bill.classify.extraction_payload",
                    return_value={"schema_version": 1, "transactions": []},
                ),
            ):
                with patch.object(
                    SyncService,
                    "_compile",
                    side_effect=ProviderError("new label"),
                ):
                    failed = flow.prepare(meta)[0]
                self.assertFalse(failed["ok"])
                self.assertFalse((incoming / "mail.zip").exists())
                self.assertEqual(
                    (root / "state/bills/archives/mail.zip").read_bytes(),
                    b"original zip",
                )
                with patch(
                    "fane.flow.bill.time.time", return_value=time.time() + 3601
                ):
                    retry = flow.pending()
                    self.assertEqual(len(retry), 1)
                    self.assertEqual(flow.pending(), [])
                saved_meta = json.loads(base64.b64decode(retry[0]["meta_b64"]))
                self.assertEqual(saved_meta, meta)
                with patch.object(
                    SyncService, "_compile", return_value=([entry], 0)
                ):
                    success = flow.prepare(saved_meta)[0]
                    self.assertTrue(success["ok"])
                    self.assertEqual(success["import"]["written"], 1)
                    replay = flow.prepare(
                        {"provider": "wechat", "file": "mail.zip"}
                    )[0]
                    self.assertTrue(replay["ok"])
                    self.assertEqual(replay["import"]["written"], 0)
                self.assertEqual(flow.pending(), [])
                self.assertEqual(
                    (root / "data/account/journal/2026/2026-11.bean")
                    .read_text()
                    .count('"Test" "Test"'),
                    1,
                )

    def test_bad_zip_is_retained_and_automatic_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "state/bills/incoming"
            incoming.mkdir(parents=True)
            (incoming / "bad.zip").write_bytes(b"bad zip")
            flow = BillFlow(root, root / "config.yaml")
            meta = {
                "provider": "wechat",
                "file": "bad.zip",
                "date": "2026-11-08",
            }
            with patch(
                "fane.flow.bill.unpack", side_effect=ValueError("bad archive")
            ):
                self.assertFalse(flow.prepare(meta)[0]["ok"])
                for attempt in range(3):
                    with patch(
                        "fane.flow.bill.time.time",
                        return_value=time.time() + (attempt + 1) * 7200,
                    ):
                        self.assertEqual(len(flow.pending()), 1)
                        self.assertFalse(flow.prepare(meta)[0]["ok"])
                with patch(
                    "fane.flow.bill.time.time",
                    return_value=time.time() + 100000,
                ):
                    self.assertEqual(flow.pending(), [])
            self.assertEqual(
                (root / "state/bills/archives/bad.zip").read_bytes(), b"bad zip"
            )


if __name__ == "__main__":
    unittest.main()
