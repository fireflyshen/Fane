#!/usr/bin/env python3
"""Export a read-only, R2-ready expense snapshot for Flux."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from beancount import loader
from beancount.core.data import Open, Transaction


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def empty_totals() -> dict[str, Decimal]:
    return {"gross": Decimal(), "refunds": Decimal(), "net": Decimal()}


def add_expense(totals: dict[str, Decimal], number: Decimal) -> None:
    totals["net"] += number
    if number > 0:
        totals["gross"] += number
    elif number < 0:
        totals["refunds"] += -number


def render_totals(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: decimal_text(values[key]) for key in ("gross", "refunds", "net")}


def expense_category_labels(entries: Iterable[Any]) -> dict[str, str]:
    return {
        entry.account: str(entry.meta["flux_label"])
        for entry in entries
        if isinstance(entry, Open)
        and entry.account.startswith("Expenses:")
        and entry.meta.get("flux_label")
    }


def category_name(account: str, labels: dict[str, str] | None = None) -> str:
    if labels and account in labels:
        return labels[account]
    parts = account.split(":")[1:]
    return " · ".join(parts[-2:] if len(parts) > 1 else parts) or account


def first_transaction_year(entries: Iterable[Any]) -> int:
    years = [entry.date.year for entry in entries if isinstance(entry, Transaction)]
    return min(years, default=date.today().year)


def expense_currencies(entries: Iterable[Any]) -> list[str]:
    currencies = {
        posting.units.currency
        for entry in entries
        if isinstance(entry, Transaction)
        for posting in entry.postings
        if posting.account.startswith("Expenses:") and posting.units is not None
    }
    return sorted(currencies)


def transaction_recognition(entry: Transaction, accrual_prefixes=()) -> str:
    """Classify expense recognition without depending on filenames or labels."""

    explicit = (entry.meta or {}).get("recognition")
    if explicit in {"accrual", "cash"}:
        return str(explicit)

    accounts = {posting.account for posting in entry.postings}
    recognizes_expense = any(account.startswith("Expenses:") for account in accounts)
    has_accrual_offset = any(
        account.startswith(tuple(accrual_prefixes)) for account in accounts
    )
    if recognizes_expense and has_accrual_offset:
        return "accrual"
    return "cash"


def build_year(
    entries: Iterable[Any], year: int, accrual_prefixes=()
) -> dict[str, Any]:
    entries = list(entries)
    category_labels = expense_category_labels(entries)
    days: dict[str, dict[str, Any]] = {}

    for entry in entries:
        if (
            not isinstance(entry, Transaction)
            or entry.date.year != year
            or entry.date > date.today()
        ):
            continue

        transaction_totals: dict[str, dict[str, Decimal]] = defaultdict(empty_totals)
        transaction_categories: list[dict[str, Any]] = []
        for posting in entry.postings:
            if not posting.account.startswith("Expenses:") or posting.units is None:
                continue
            number = posting.units.number
            currency = posting.units.currency
            add_expense(transaction_totals[currency], number)
            transaction_categories.append(
                {
                    "account": posting.account,
                    "name": category_name(posting.account, category_labels),
                    "currency": currency,
                    "number": number,
                }
            )

        if not transaction_categories:
            continue

        date_key = entry.date.isoformat()
        day = days.setdefault(
            date_key,
            {
                "date": date_key,
                "totals": defaultdict(empty_totals),
                "categories": {},
                "transactions": [],
            },
        )

        for currency, totals in transaction_totals.items():
            for field, value in totals.items():
                day["totals"][currency][field] += value

        rendered_transaction_categories = []
        for category in transaction_categories:
            category_key = (category["account"], category["currency"])
            aggregate = day["categories"].setdefault(
                category_key,
                {
                    "account": category["account"],
                    "name": category["name"],
                    "currency": category["currency"],
                    **empty_totals(),
                },
            )
            add_expense(aggregate, category["number"])
            item_totals = empty_totals()
            add_expense(item_totals, category["number"])
            rendered_transaction_categories.append(
                {
                    "account": category["account"],
                    "name": category["name"],
                    "currency": category["currency"],
                    **render_totals(item_totals),
                }
            )

        meta = entry.meta or {}
        filename = Path(str(meta.get("filename", ""))).name
        line = meta.get("lineno")
        source = f"{filename}:{line}" if filename and line else filename or None
        recognition = transaction_recognition(entry, accrual_prefixes)
        day["transactions"].append(
            {
                "id": f"{date_key}:{source or len(day['transactions'])}",
                "payee": entry.payee,
                "narration": entry.narration,
                "source": source,
                "kind": recognition,
                "recognition": recognition,
                "amounts": {
                    currency: render_totals(totals)
                    for currency, totals in sorted(transaction_totals.items())
                },
                "categories": rendered_transaction_categories,
            }
        )

    rendered_days = []
    for date_key in sorted(days):
        day = days[date_key]
        categories = []
        for category in day["categories"].values():
            categories.append(
                {
                    "account": category["account"],
                    "name": category["name"],
                    "currency": category["currency"],
                    **render_totals(category),
                }
            )
        categories.sort(
            key=lambda item: (item["currency"], -Decimal(item["net"]), item["account"])
        )
        rendered_days.append(
            {
                "date": date_key,
                "totals": {
                    currency: render_totals(totals)
                    for currency, totals in sorted(day["totals"].items())
                },
                "categories": categories,
                "transactions": day["transactions"],
            }
        )

    return {
        "schemaVersion": 1,
        "year": year,
        "firstYear": first_transaction_year(entries),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "currencies": expense_currencies(entries),
        "days": rendered_days,
    }


def build_snapshot(
    entries: Iterable[Any],
    version: str,
    *,
    include_transactions: bool = False,
    accrual_prefixes=(),
) -> dict[str, Any]:
    entries = list(entries)
    first_year = first_transaction_year(entries)
    current_year = date.today().year
    years = {
        str(year): build_year(entries, year, accrual_prefixes)
        for year in range(first_year, current_year + 1)
    }
    for year in years.values():
        for day in year["days"]:
            if not include_transactions:
                day["transactions"] = []
                continue
            # The private cloud copy needs drawer details, not local ledger paths.
            # Replace source-derived IDs as well so filenames and line numbers never
            # leave the Bills repository.
            for index, transaction in enumerate(day["transactions"], start=1):
                transaction.pop("source", None)
                transaction["id"] = f"{day['date']}:{index}"
    return {
        "schemaVersion": 1,
        "version": version,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "firstYear": first_year,
        "currencies": expense_currencies(entries),
        "detailLevel": "transactions" if include_transactions else "summary",
        "years": years,
    }


def write_json(payload: dict[str, Any], output: Path | None) -> None:
    if output is None:
        json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(output)


def export_snapshot(
    ledger: Path,
    *,
    year: int | None = None,
    meta: bool = False,
    version: str = "local",
    include_transactions: bool = False,
    accrual_prefixes=(),
) -> dict:
    entries, errors, _ = loader.load_file(str(ledger))
    if errors:
        raise ValueError("Cannot export an invalid ledger: " + str(errors[0]))
    if meta:
        return {
            "firstYear": first_transaction_year(entries),
            "currencies": expense_currencies(entries),
        }
    if year is not None:
        return build_year(entries, year, accrual_prefixes)
    return build_snapshot(
        entries,
        version,
        include_transactions=include_transactions,
        accrual_prefixes=accrual_prefixes,
    )
