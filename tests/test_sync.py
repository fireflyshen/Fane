import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "main.py", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write_wechat(path: Path, rows: list[tuple[str, str]]) -> None:
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
    for timestamp, order_id in rows:
        sheet.append(
            [
                timestamp,
                order_id,
                "/",
                "支出",
                "测试商户",
                f"测试商品-{order_id}",
                "12.34",
                "支付成功",
                "零钱",
                "商户消费",
            ]
        )
    workbook.save(path)


def write_config(
    path: Path,
    source_template: Path,
    journal: Path,
    *,
    classified: bool = True,
    validator: bool = False,
) -> None:
    rules = (
        "wechat:\n"
        "  rules:\n"
        "    - peer: 测试商户\n"
        "      target-account: Expenses:Test\n"
        "    - method: 零钱\n"
        "      method-account: Assets:Cash:WeChat\n"
        if classified
        else ""
    )
    validators = (
        "    validators:\n"
        "      - command: [/usr/bin/false]\n"
        if validator
        else ""
    )
    path.write_text(
        "default-minus-account: Assets:FIXME\n"
        "default-plus-account: Expenses:FIXME\n"
        "default-currency: CNY\n"
        f"{rules}"
        "jobs:\n"
        "  daily:\n"
        "    timezone: Asia/Shanghai\n"
        f"    journal-dir: {journal}\n"
        "    on-missing: skip\n"
        "    require-classified: true\n"
        "    routing:\n"
        "      expense: '{year}/{year}-{month}.bean'\n"
        "      income: '{year}/income.bean'\n"
        "    sources:\n"
        "      - id: wechat-daily\n"
        "        provider: wechat\n"
        f"        path: '{source_template}'\n"
        f"{validators}",
        encoding="utf-8",
    )


class SyncCliTest(unittest.TestCase):
    def test_sync_is_incremental_idempotent_and_routes_by_entry_year(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_template = root / "wechat-{date}.xlsx"
            source = root / "wechat-2026-01-05.xlsx"
            config = root / "config.yaml"
            journal = root / "journal"
            write_wechat(source, [("2025-12-31 23:50:00", "order-old")])
            write_config(config, source_template, journal)

            first = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )
            unchanged = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )
            write_wechat(
                source,
                [
                    ("2025-12-31 23:50:00", "order-old"),
                    ("2026-01-05 08:00:00", "order-new"),
                ],
            )
            changed = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )

            old_text = (journal / "2025" / "2025-12.bean").read_text(encoding="utf-8")
            new_text = (journal / "2026" / "2026-01.bean").read_text(encoding="utf-8")
            index_lines = (root / ".fane" / "imported.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["written"], 1)
        self.assertEqual(json.loads(unchanged.stdout)["status"], "noop")
        self.assertEqual(changed.returncode, 0, changed.stderr)
        self.assertEqual(json.loads(changed.stdout)["written"], 1)
        self.assertEqual(json.loads(changed.stdout)["skipped"], 1)
        self.assertEqual(old_text.count("2025-12-31 *"), 1)
        self.assertEqual(new_text.count("2026-01-05 *"), 1)
        self.assertEqual(len(index_lines), 2)

    def test_missing_source_is_a_successful_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.yaml"
            write_config(config, root / "wechat-{date}.xlsx", root / "journal")

            result = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["sources"][0]["status"], "missing")

    def test_unclassified_transactions_do_not_write_or_advance_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat-2026-01-05.xlsx"
            config = root / "config.yaml"
            journal = root / "journal"
            write_wechat(source, [("2026-01-05 08:00:00", "unclassified")])
            write_config(
                config, root / "wechat-{date}.xlsx", journal, classified=False
            )

            result = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )

            state_exists = (root / ".fane" / "sync-state.json").exists()
            journal_files = list(journal.rglob("*.bean")) if journal.exists() else []

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("拒绝同步", result.stderr)
        self.assertFalse(state_exists)
        self.assertEqual(journal_files, [])

    def test_validator_failure_rolls_back_journal_index_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wechat-2026-01-05.xlsx"
            config = root / "config.yaml"
            journal = root / "journal"
            write_wechat(source, [("2026-01-05 08:00:00", "existing")])
            write_config(config, root / "wechat-{date}.xlsx", journal)
            initial = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )
            target = journal / "2026" / "2026-01.bean"
            index = root / ".fane" / "imported.jsonl"
            state = root / ".fane" / "sync-state.json"
            before = (target.read_bytes(), index.read_bytes(), state.read_bytes())

            write_wechat(
                source,
                [
                    ("2026-01-05 08:00:00", "existing"),
                    ("2026-01-05 09:00:00", "rolled-back"),
                ],
            )
            write_config(
                config,
                root / "wechat-{date}.xlsx",
                journal,
                validator=True,
            )

            result = run_cli(
                "--config", str(config), "sync", "daily", "--date", "2026-01-05", "--json"
            )

            after = (target.read_bytes(), index.read_bytes(), state.read_bytes())

        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("校验命令失败", result.stderr)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
