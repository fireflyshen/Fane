import unittest
from datetime import date
from decimal import Decimal

from beancount import loader
from beancount.core.data import Transaction

from fane.subscriptions.service import GeneratedEntry, Subscription


class SharedRenderingTest(unittest.TestCase):
    def test_subscription_preserves_strings_precision_and_long_account_alignment(self):
        debit = "Expenses:Technology:" + "LongAccount" * 5
        credit = "Assets:Cash"
        sub = Subscription(
            id='service-"quoted"\\id',
            status="active",
            kind="expense",
            interval="monthly",
            payee='A & B <Cloud> "quoted"\\name',
            narration="Monthly\nsubscription",
            debit_account=debit,
            credit_account=credit,
            amount=Decimal("1234567890.1234"),
            currency="USD",
            billing_day=5,
            start_date=date(2026, 1, 1),
            end_date=None,
        )
        content = GeneratedEntry(sub, date(2026, 10, 5), "2026-10").render()
        entries, errors, _ = loader.load_string(
            f"2020-01-01 open {debit} USD\n2020-01-01 open {credit} USD\n" + content
        )
        self.assertEqual(errors, [])
        entry = next(e for e in entries if isinstance(e, Transaction))
        self.assertEqual(entry.payee, sub.payee)
        self.assertEqual(entry.narration, sub.narration)
        self.assertEqual(entry.meta["subscription_id"], sub.id)
        self.assertEqual(entry.meta["period"], "2026-10")
        self.assertEqual(
            [p.units.number for p in entry.postings], [sub.amount, -sub.amount]
        )
        postings = [line for line in content.splitlines() if line.endswith(" USD")]
        self.assertEqual(postings[0].index(" USD"), postings[1].index(" USD"))


if __name__ == "__main__":
    unittest.main()
