import tempfile
import unittest
from datetime import date
from pathlib import Path

from package.compiler.results import RenderedEntry
from package.compiler.writer import JournalWriter
from package.template.template import get_template


class BeancountFormatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.content = get_template("normal.j2").render(
            pay_time=date(2026, 9, 13),
            peer="测试商户",
            item="测试商品",
            note="",
            money=12,
            commission=0,
            plus_account="Expenses:Life:Logistics",
            minus_account="Liabilities:CreditCard:ICBC-8393",
            plus_str="",
            minus_str="",
            pnl_account="",
            commission_account="",
            currency="CNY",
            metadata={"source": "WeChat"},
            tags=[],
        )

    def test_template_matches_bills_indentation_and_currency_column(self) -> None:
        indented_lines = self.content.splitlines()[1:]
        self.assertTrue(indented_lines)
        self.assertTrue(all(line.startswith("    ") for line in indented_lines if line))

        posting_lines = [line for line in indented_lines if line.endswith(" CNY")]
        self.assertEqual(len(posting_lines), 2)
        self.assertTrue(all(line.index("CNY") == 71 for line in posting_lines))

    def test_writer_leaves_two_blank_lines_between_entries(self) -> None:
        entry = RenderedEntry(
            date=date(2026, 9, 13),
            month="09",
            kind="expense",
            fingerprint="wechat:test",
            content=self.content,
            source_provider="wechat",
            source_file="test.xlsx",
            order_id="test-order",
        )

        with tempfile.TemporaryDirectory() as directory:
            writer = JournalWriter(
                directory,
                dedupe_index=Path(directory) / ".fane" / "imported.jsonl",
            )
            writer.write([entry])
            target = Path(directory) / "2026" / "2026-09.bean"
            output = target.read_text(encoding="utf-8")

        self.assertTrue(output.endswith("\n\n\n"))


if __name__ == "__main__":
    unittest.main()
