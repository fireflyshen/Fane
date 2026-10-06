from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from beancount import loader
from beancount.core.data import Close, Open


def calculate_balances(
    ledger_path: Path,
    cutoff_date: dt.date,
    include_internal: bool = False,
    ignored_prefixes=(),
) -> list[tuple[str, str, Decimal]]:
    """Calculate account balances strictly before cutoff_date."""
    entries, errors, options = loader.load_file(str(ledger_path))

    if errors:
        raise ValueError("Cannot generate assertions from an invalid ledger")

    # Identify open and closed accounts
    open_dates: dict[str, dt.date] = {}
    account_currencies: dict[str, set[str]] = defaultdict(set)
    closed_accounts: set[str] = set()

    for entry in entries:
        if isinstance(entry, Open) and entry.date < cutoff_date:
            open_dates[entry.account] = entry.date
            if entry.currencies:
                account_currencies[entry.account].update(entry.currencies)
        elif isinstance(entry, Close):
            if entry.date <= cutoff_date:
                closed_accounts.add(entry.account)

    operating_currencies = set(options.get("operating_currency", []))
    balances = defaultdict(lambda: defaultdict(Decimal))

    for entry in entries:
        if hasattr(entry, "date") and entry.date < cutoff_date:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    balances[posting.account][posting.units.currency] += (
                        posting.units.number
                    )

    results = []
    for account in sorted(open_dates.keys()):
        if not (account.startswith("Assets:") or account.startswith("Liabilities:")):
            continue
        if account in closed_accounts:
            continue
        if not include_internal and any(
            account.startswith(prefix) for prefix in ignored_prefixes
        ):
            continue

        # Check currencies with activity or configured for this account
        configured_curr = account_currencies.get(account, set())
        active_curr = set(balances[account].keys())
        currencies = sorted(configured_curr | active_curr)
        if not currencies:
            currencies = sorted(operating_currencies)

        for curr in currencies:
            amt = balances[account].get(curr, Decimal("0.00"))
            results.append((account, curr, amt))

    return results


def render_assertions(
    assertions: list[tuple[str, str, Decimal]],
    assertion_date: dt.date,
    precision: int = 2,
) -> str:
    lines = [
        f"; Balance assertions as of {assertion_date:%Y-%m-%d} (start of day)",
        f"; Asserting activity through {(assertion_date - dt.timedelta(days=1)):%Y-%m-%d}",
        "",
    ]
    for account, curr, amt in assertions:
        lines.append(
            f"{assertion_date:%Y-%m-%d} balance {account:45} {format(amt, f'.{precision}f'):>12} {curr}"
        )
    lines.append("")
    return "\n".join(lines)


def update_index(index_file: Path, target_rel_path: str) -> None:
    content = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    include_line = f'include "{target_rel_path}"'
    if include_line not in content:
        lines = [line for line in content.splitlines() if line.strip()]
        lines.append(include_line)
        # Keep includes sorted for consistency
        include_lines = sorted({line for line in lines if line.startswith("include ")})
        other_lines = [line for line in lines if not line.startswith("include ")]
        new_content = "\n".join(other_lines + include_lines) + "\n"
        index_file.write_text(new_content, encoding="utf-8")


def write_assertions(output: Path, index: Path, text: str) -> None:
    import os
    import tempfile

    relative = os.path.relpath(output, index.parent)
    originals = {
        path: path.read_bytes() if path.exists() else None for path in (output, index)
    }
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        index.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        try:
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        update_index(index, relative.replace(os.sep, "/"))
    except Exception:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
