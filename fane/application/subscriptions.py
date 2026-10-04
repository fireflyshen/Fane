#!/usr/bin/env python3
"""Generate recurring subscription transactions from JSON config.

Default mode is dry-run. Use --write to append missing generated entries.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from beancount import loader
from beancount.core.data import Open, Transaction

GENERATED_BY = "tools/generate_subscriptions.py"


@dataclass(frozen=True)
class Subscription:
    id: str
    status: str
    kind: str
    interval: str
    payee: str
    narration: str
    debit_account: str
    credit_account: str
    amount: Decimal
    currency: str
    billing_day: int
    start_date: dt.date
    end_date: dt.date | None


@dataclass(frozen=True)
class GeneratedEntry:
    subscription: Subscription
    date: dt.date
    period: str

    def target_path(self, root: Path) -> Path:
        return (
            root
            / "journal"
            / str(self.date.year)
            / f"{self.date.year}-{self.date.month:02d}.bean"
        )

    def render(self) -> str:
        amount = format_decimal(self.subscription.amount)
        return (
            f"\n{self.date:%Y-%m-%d} * {json.dumps(self.subscription.payee, ensure_ascii=False)} {json.dumps(self.subscription.narration, ensure_ascii=False)}\n"
            f"    subscription_id: {json.dumps(self.subscription.id, ensure_ascii=False)}\n"
            f'    subscription_type: "{self.subscription.kind}"\n'
            f'    generated_by: "{GENERATED_BY}"\n'
            f'    period: "{self.period}"\n'
            f"    {self.subscription.debit_account}    {amount} {self.subscription.currency}\n"
            f"    {self.subscription.credit_account}   -{amount} {self.subscription.currency}\n"
        )


def parse_date(value: str, field: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD: {value!r}") from exc


def parse_amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"amount must be a positive decimal: {value!r}") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"amount must be positive: {value!r}")
    return amount


def format_decimal(value: Decimal) -> str:
    return format(value, "f")


def month_iter(start: dt.date, until: dt.date):
    year, month = start.year, start.month
    while (year, month) <= (until.year, until.month):
        yield year, month
        month += 1
        if month == 13:
            year += 1
            month = 1


def billing_date(year: int, month: int, day: int) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last_day))


def parse_month(value: str) -> tuple[dt.date, dt.date]:
    try:
        year, month = map(int, value.split("-", 1))
        start = dt.date(year, month, 1)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"--month must be YYYY-MM: {value!r}") from exc
    end = dt.date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def load_subscriptions(config_path: Path) -> list[Subscription]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("subscription config must be a JSON array")

    subscriptions = []
    seen_ids = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"subscription #{index} must be an object")

        sub_id = item.get("id")
        if not isinstance(sub_id, str) or not sub_id.strip():
            raise ValueError(f"subscription #{index} is missing id")
        if sub_id in seen_ids:
            raise ValueError(f"duplicate subscription id: {sub_id}")
        seen_ids.add(sub_id)

        status = item.get("status", "active")
        if status not in {"active", "paused", "cancelled"}:
            raise ValueError(f"{sub_id}: status must be active, paused or cancelled")

        kind = item.get("type", "expense")
        if kind not in {"expense", "transfer"}:
            raise ValueError(f"{sub_id}: type must be expense or transfer")

        interval = item.get("interval", "monthly")
        if interval != "monthly":
            raise ValueError(f"{sub_id}: only monthly interval is currently supported")

        debit_account = item.get("debit_account") or item.get("expense_account")
        credit_account = item.get("credit_account") or item.get("asset_account")
        if not debit_account or not credit_account:
            raise ValueError(f"{sub_id}: debit_account and credit_account are required")
        if not item.get("payee"):
            raise ValueError(f"{sub_id}: payee is required")
        if not item.get("narration"):
            raise ValueError(f"{sub_id}: narration is required")

        for field in ("payee", "narration", "currency"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"{sub_id}: {field} must be a non-empty string")
        if not isinstance(debit_account, str) or not isinstance(credit_account, str):
            raise ValueError(f"{sub_id}: accounts must be strings")

        raw_day = item.get("billing_day", item.get("day_of_month", 1))
        try:
            billing_day = int(raw_day)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{sub_id}: billing_day must be an integer") from exc
        if isinstance(raw_day, (bool, float)):
            raise ValueError(f"{sub_id}: billing_day must be an integer")
        if not 1 <= billing_day <= 31:
            raise ValueError(f"{sub_id}: billing_day must be 1..31")

        start_date = parse_date(item.get("start_date"), f"{sub_id}.start_date")
        end_date = item.get("end_date")
        parsed_end_date = (
            parse_date(end_date, f"{sub_id}.end_date") if end_date else None
        )
        if parsed_end_date and parsed_end_date < start_date:
            raise ValueError(f"{sub_id}: end_date must not be before start_date")

        subscriptions.append(
            Subscription(
                id=sub_id,
                status=status,
                kind=kind,
                interval=interval,
                payee=item.get("payee", ""),
                narration=item.get("narration", ""),
                debit_account=debit_account,
                credit_account=credit_account,
                amount=parse_amount(item.get("amount")),
                currency=item.get("currency", ""),
                billing_day=billing_day,
                start_date=start_date,
                end_date=parsed_end_date,
            )
        )

    return subscriptions


def load_ledger_state(ledger: Path):
    entries, errors, options = loader.load_file(str(ledger))
    if errors:
        raise ValueError("main.bean has Beancount errors; run fa ledger validate first")

    open_accounts = {entry.account for entry in entries if isinstance(entry, Open)}
    operating_currencies = set(options.get("operating_currency", []))
    generated_keys = set()
    legacy_fingerprints = set()

    for entry in entries:
        if not isinstance(entry, Transaction):
            continue

        subscription_id = entry.meta.get("subscription_id")
        period = entry.meta.get("period")
        if subscription_id and period:
            generated_keys.add((subscription_id, period))

        for posting in entry.postings:
            if posting.units and posting.units.number is not None:
                amount = format_decimal(abs(posting.units.number))
                legacy_fingerprints.add(
                    (
                        entry.date.year,
                        entry.date.month,
                        entry.payee or "",
                        entry.narration or "",
                        posting.account,
                        amount,
                        posting.units.currency,
                    )
                )

    return open_accounts, operating_currencies, generated_keys, legacy_fingerprints


def validate_subscriptions(subscriptions, open_accounts, operating_currencies):
    failures = []
    for sub in subscriptions:
        for account in (sub.debit_account, sub.credit_account):
            if account not in open_accounts:
                failures.append(f"{sub.id}: account is not open: {account}")
        if sub.currency not in operating_currencies:
            failures.append(
                f"{sub.id}: currency is not an operating currency: {sub.currency}"
            )
        if sub.kind == "expense" and not sub.debit_account.startswith("Expenses:"):
            failures.append(f"{sub.id}: expense subscriptions should debit Expenses:*")
        if sub.kind == "transfer" and sub.debit_account.startswith("Expenses:"):
            failures.append(
                f"{sub.id}: transfer subscriptions should not debit Expenses:*"
            )
    return failures


def generate_entries(subscriptions, start, until, generated_keys, legacy_fingerprints):
    entries = []
    for sub in subscriptions:
        if sub.status != "active":
            continue
        effective_until = min(until, sub.end_date) if sub.end_date else until
        effective_start = max(start, sub.start_date)
        if effective_until < effective_start:
            continue

        for year, month in month_iter(effective_start, effective_until):
            date = billing_date(year, month, sub.billing_day)
            if date < effective_start or date > effective_until:
                continue
            period = f"{year}-{month:02d}"
            key = (sub.id, period)
            legacy = (
                year,
                month,
                sub.payee,
                sub.narration,
                sub.debit_account,
                format_decimal(sub.amount),
                sub.currency,
            )
            if key in generated_keys or legacy in legacy_fingerprints:
                continue
            entries.append(GeneratedEntry(sub, date, period))
    return entries


def update_indexes(generated_entries, root: Path):
    touched_years = sorted({entry.date.year for entry in generated_entries})
    for year in touched_years:
        year_dir = root / "journal" / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        index_path = year_dir / "index.bean"
        months = sorted(
            {entry.date.month for entry in generated_entries if entry.date.year == year}
        )

        content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        lines = content.splitlines()
        for month in months:
            include = f'include "{year}-{month:02d}.bean"'
            commented = f"; {include}"
            if include in lines:
                continue
            if commented in lines:
                lines = [include if line == commented else line for line in lines]
            else:
                lines.append(include)
        index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    journal_index = root / "journal" / "index.bean"
    content = (
        journal_index.read_text(encoding="utf-8") if journal_index.exists() else ""
    )
    lines = content.splitlines()
    for year in touched_years:
        include = f'include "./{year}/index.bean"'
        alt_include = f'include "{year}/index.bean"'
        if include not in lines and alt_include not in lines:
            lines.append(include)
    journal_index.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_entries(generated_entries, root: Path):
    by_path = {}
    for entry in generated_entries:
        by_path.setdefault(entry.target_path(root), []).append(entry)

    for path, entries in by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(entry.render())

    update_indexes(generated_entries, root)


class SubscriptionService:
    """Check and generate subscription entries for one explicit ledger."""

    def __init__(self, ledger: Path, subscriptions: Path):
        self.ledger = ledger.expanduser().resolve()
        self.root = self.ledger.parent
        self.subscriptions = subscriptions.expanduser().resolve()

    def _load(self):
        subscriptions = load_subscriptions(self.subscriptions)
        accounts, currencies, generated, legacy = load_ledger_state(self.ledger)
        failures = validate_subscriptions(subscriptions, accounts, currencies)
        if failures:
            raise ValueError("订阅配置检查失败: " + "; ".join(failures))
        return subscriptions, generated, legacy

    def check(self) -> dict:
        subscriptions, _, _ = self._load()
        return {
            "status": "valid",
            "subscriptions": len(subscriptions),
            "ledger": str(self.ledger),
        }

    def generate(
        self, *, month: str | None = None, until: str | None = None, write: bool = False
    ) -> dict:
        if month and until:
            raise ValueError("--month 与 --until 不能同时使用")
        if month:
            start, end = parse_month(month)
        else:
            start, end = (
                dt.date.min,
                parse_date(until or dt.date.today().isoformat(), "--until"),
            )
        subscriptions, generated, legacy = self._load()
        entries = generate_entries(subscriptions, start, end, generated, legacy)
        report = {
            "status": "dry-run" if not write else ("written" if entries else "noop"),
            "total": len(entries),
            "written": len(entries) if write else 0,
            "entries": [
                {
                    "subscription_id": entry.subscription.id,
                    "date": entry.date.isoformat(),
                    "period": entry.period,
                    "target": str(entry.target_path(self.root)),
                    "content": entry.render(),
                }
                for entry in entries
            ],
        }
        if write and entries:
            targets = {entry.target_path(self.root) for entry in entries}
            targets.update(
                self.root / "journal" / str(entry.date.year) / "index.bean"
                for entry in entries
            )
            targets.add(self.root / "journal" / "index.bean")
            snapshots = {
                path: path.read_bytes() if path.exists() else None for path in targets
            }
            try:
                write_entries(entries, self.root)
                _, _, visible, _ = load_ledger_state(self.ledger)
                if any(
                    (entry.subscription.id, entry.period) not in visible
                    for entry in entries
                ):
                    raise ValueError(
                        "生成分录未被主账本引用；请让主账本 include journal/index.bean"
                    )
            except Exception:
                for path, content in snapshots.items():
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(content)
                raise
        return report
