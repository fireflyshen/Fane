#!/usr/bin/env python3
"""Query a date range from the Bills Beancount ledger and emit JSON.

This is a read-only bridge for automation tools such as n8n. It loads the
complete ledger through Beancount, filters transactions by date, and exposes
economic totals without treating balance-sheet transfers as income/expenses.

Example:

    fa query 2026-07-27 2026-08-02

Amounts are JSON strings, not floating-point numbers, so decimal precision is
preserved. The date range is inclusive and limited to 366 days per invocation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from beancount import loader
from beancount.core.amount import Amount
from beancount.core.data import Transaction

MAX_QUERY_DAYS = 366
DEFAULT_MAX_TRANSACTIONS = 500

INTERNAL_META_KEYS = frozenset({"filename", "lineno", "__tolerances__"})


def decimal_text(value: Decimal) -> str:
    """Render Decimal without exponent notation or binary conversion."""

    return format(value, "f")


def add_amount(target: dict[str, Decimal], currency: str, number: Decimal) -> None:
    target[currency] += number


def rendered_amounts(amounts: dict[str, Decimal]) -> dict[str, str]:
    return {
        currency: decimal_text(number)
        for currency, number in sorted(amounts.items())
        if number != 0
    }


def rendered_account_amounts(
    amounts: dict[str, dict[str, Decimal]],
) -> dict[str, dict[str, str]]:
    return {
        account: rendered_amounts(currency_amounts)
        for account, currency_amounts in sorted(amounts.items())
        if rendered_amounts(currency_amounts)
    }


def json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def public_metadata(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    return {
        key: json_scalar(value)
        for key, value in sorted(meta.items())
        if key not in INTERNAL_META_KEYS and not key.startswith("__")
    }


def source_location(
    meta: dict[str, Any] | None, ledger_root: Path = Path("/bills")
) -> str | None:
    if not meta:
        return None
    filename = meta.get("filename")
    line = meta.get("lineno")
    if not filename:
        return None

    path = Path(filename)
    try:
        path = path.resolve().relative_to(ledger_root.resolve())
    except (OSError, ValueError):
        pass

    return f"{path}:{line}" if line is not None else str(path)


def serialize_amount(amount: Amount | None) -> dict[str, str] | None:
    if amount is None:
        return None
    return {
        "number": decimal_text(amount.number),
        "currency": amount.currency,
    }


def serialize_cost(cost: Any) -> dict[str, Any] | None:
    if cost is None:
        return None
    result = {
        "number": decimal_text(cost.number) if cost.number is not None else None,
        "currency": cost.currency,
    }
    if getattr(cost, "date", None) is not None:
        result["date"] = cost.date.isoformat()
    if getattr(cost, "label", None) is not None:
        result["label"] = cost.label
    return result


def posting_account_type(account: str) -> str:
    return account.partition(":")[0]


def transaction_kind(entry: Transaction) -> str:
    account_types = {
        posting_account_type(posting.account) for posting in entry.postings
    }
    expense_numbers = [
        posting.units.number
        for posting in entry.postings
        if posting.account.startswith("Expenses:") and posting.units is not None
    ]
    income_numbers = [
        posting.units.number
        for posting in entry.postings
        if posting.account.startswith("Income:") and posting.units is not None
    ]

    if expense_numbers and income_numbers:
        return "mixed_income_expense"
    if any(number > 0 for number in expense_numbers):
        return "expense"
    if expense_numbers:
        return "refund"
    if income_numbers:
        if any(number < 0 for number in income_numbers):
            return "income"
        return "income_reversal"

    liability_numbers = [
        posting.units.number
        for posting in entry.postings
        if posting.account.startswith("Liabilities:") and posting.units is not None
    ]
    if liability_numbers:
        if all(number >= 0 for number in liability_numbers):
            return "liability_settlement"
        if all(number <= 0 for number in liability_numbers):
            return "liability_increase"
        return "liability_transfer"
    if account_types and account_types <= {"Assets"}:
        return "asset_transfer"
    if "Equity" in account_types:
        return "equity_transfer"
    return "balance_sheet_transfer"


def transaction_recognition(entry: Transaction) -> str:
    """Separate cash-like activity from accrual and prepayment recognition."""

    explicit = (entry.meta or {}).get("recognition")
    if explicit in {"accrual", "cash"}:
        return str(explicit)

    accounts = {posting.account for posting in entry.postings}
    recognizes_expense = any(account.startswith("Expenses:") for account in accounts)
    offsets_accrued_liability = any(
        account.startswith(("Liabilities:Accrued:", "Liabilities:AccruedExpenses:"))
        for account in accounts
    )
    consumes_prepayment = any(
        account.startswith(("Assets:Prepaid:", "Assets:PrepaidExpenses:"))
        for account in accounts
    )
    if recognizes_expense and (offsets_accrued_liability or consumes_prepayment):
        return "accrual"
    return "cash"


def posting_json(posting: Any) -> dict[str, Any]:
    return {
        "account": posting.account,
        "account_type": posting_account_type(posting.account),
        "units": serialize_amount(posting.units),
        "cost": serialize_cost(posting.cost),
        "price": serialize_amount(posting.price),
        "flag": posting.flag,
        "meta": public_metadata(posting.meta),
    }


def transaction_json(
    entry: Transaction, ledger_root: Path = Path("/bills")
) -> dict[str, Any]:
    return {
        "date": entry.date.isoformat(),
        "flag": entry.flag,
        "payee": entry.payee,
        "narration": entry.narration,
        "kind": transaction_kind(entry),
        "recognition": transaction_recognition(entry),
        "tags": sorted(entry.tags or ()),
        "links": sorted(entry.links or ()),
        "source": source_location(entry.meta, ledger_root),
        "meta": public_metadata(entry.meta),
        "postings": [posting_json(posting) for posting in entry.postings],
    }


def query_entries(
    entries: Iterable[Any],
    start_date: date,
    end_date: date,
    *,
    max_transactions: int = DEFAULT_MAX_TRANSACTIONS,
    ledger_root: Path = Path("/bills"),
) -> dict[str, Any]:
    selected = [
        entry
        for entry in entries
        if isinstance(entry, Transaction) and start_date <= entry.date <= end_date
    ]
    selected.sort(
        key=lambda entry: (
            entry.date,
            source_location(entry.meta, ledger_root) or "",
            entry.payee or "",
            entry.narration,
        )
    )

    gross_income: dict[str, Decimal] = defaultdict(Decimal)
    income_reversals: dict[str, Decimal] = defaultdict(Decimal)
    net_income: dict[str, Decimal] = defaultdict(Decimal)
    gross_expenses: dict[str, Decimal] = defaultdict(Decimal)
    expense_refunds: dict[str, Decimal] = defaultdict(Decimal)
    net_expenses: dict[str, Decimal] = defaultdict(Decimal)
    income_by_account: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    expenses_by_account: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    balance_sheet_changes: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    kind_counts: dict[str, int] = defaultdict(int)
    warnings: list[str] = []

    for entry in selected:
        kind_counts[transaction_kind(entry)] += 1
        for posting in entry.postings:
            if posting.units is None:
                warnings.append(
                    f"{entry.date}: {posting.account} has no resolved units"
                )
                continue

            number = posting.units.number
            currency = posting.units.currency
            if posting.account.startswith("Income:"):
                economic_amount = -number
                add_amount(net_income, currency, economic_amount)
                add_amount(
                    income_by_account[posting.account], currency, economic_amount
                )
                if number < 0:
                    add_amount(gross_income, currency, -number)
                elif number > 0:
                    add_amount(income_reversals, currency, number)
            elif posting.account.startswith("Expenses:"):
                add_amount(net_expenses, currency, number)
                add_amount(expenses_by_account[posting.account], currency, number)
                if number > 0:
                    add_amount(gross_expenses, currency, number)
                elif number < 0:
                    add_amount(expense_refunds, currency, -number)
            else:
                add_amount(balance_sheet_changes[posting.account], currency, number)

    returned = selected[:max_transactions]
    truncated = len(returned) < len(selected)
    if truncated:
        warnings.append(
            f"transaction details truncated to {max_transactions}; totals include all "
            f"{len(selected)} transactions"
        )

    return {
        "schema_version": 1,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days_inclusive": (end_date - start_date).days + 1,
        },
        "statistics": {
            "transaction_count": len(selected),
            "returned_transaction_count": len(returned),
            "truncated": truncated,
            "transaction_kinds": dict(sorted(kind_counts.items())),
        },
        "totals": {
            "income": {
                "gross": rendered_amounts(gross_income),
                "reversals": rendered_amounts(income_reversals),
                "net": rendered_amounts(net_income),
            },
            "expenses": {
                "gross": rendered_amounts(gross_expenses),
                "refunds": rendered_amounts(expense_refunds),
                "net": rendered_amounts(net_expenses),
            },
        },
        "income_by_account": rendered_account_amounts(income_by_account),
        "expenses_by_account": rendered_account_amounts(expenses_by_account),
        "balance_sheet_changes": rendered_account_amounts(balance_sheet_changes),
        "transactions": [transaction_json(entry, ledger_root) for entry in returned],
        "warnings": warnings,
    }


def load_ledger(path: Path) -> list[Any]:
    entries, errors, _ = loader.load_file(str(path))
    if errors:
        rendered = "\n".join(str(error) for error in errors[:20])
        raise ValueError(
            f"ledger validation failed with {len(errors)} error(s):\n{rendered}"
        )
    return entries


class BeancountQuery:
    def __init__(self, ledger: Path):
        self.ledger = ledger

    def query(self, start, end, limit):
        result = query_entries(
            load_ledger(self.ledger),
            start,
            end,
            max_transactions=limit,
            ledger_root=Path("/"),
        )
        result["ledger"] = str(self.ledger)
        return result
