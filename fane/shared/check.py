from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from beancount import loader
from beancount.core.account import TYPE as ACCOUNT_TYPE
from beancount.core.data import Balance, Close, Custom, Open, Pad, Transaction

from fane.shared.config.ledger import Policy

INCLUDE_RE = re.compile(r'^\s*include\s+"([^"]+)"')

ACCOUNT_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z])(?:Assets|Liabilities|Income|Expenses|Equity)"
    r"(?::[A-Za-z0-9-]+)+"
)


def ambiguous_account_segments(
    accounts, allowed_accounts=frozenset(), disallowed_segments=frozenset()
) -> dict[str, tuple[str, ...]]:
    failures = {}
    denied = {s.casefold() for s in disallowed_segments}
    for account in sorted(accounts):
        if account in allowed_accounts:
            continue
        matches = tuple(
            segment for segment in account.split(":") if segment.casefold() in denied
        )
        if matches:
            failures[account] = matches
    return failures


def unused_open_accounts(opens, first_usage) -> list[str]:
    return sorted(set(opens) - set(first_usage))


def account_values(custom: Custom) -> set[str]:
    accounts = set()
    for value in custom.values:
        if getattr(value, "dtype", None) == ACCOUNT_TYPE:
            accounts.add(value.value)
    return accounts


def used_accounts(entries) -> dict[str, object]:
    first_usage = {}
    for entry in entries:
        accounts = set()
        if isinstance(entry, Transaction):
            accounts.update(posting.account for posting in entry.postings)
        elif isinstance(entry, Balance):
            accounts.add(entry.account)
        elif isinstance(entry, Pad):
            accounts.add(entry.account)
            accounts.add(entry.source_account)
        elif isinstance(entry, Close):
            accounts.add(entry.account)
        elif isinstance(entry, Custom):
            accounts.update(account_values(entry))

        for account in accounts:
            first_usage.setdefault(account, entry)
    return first_usage


def commodities_used(entries) -> set[str]:
    commodities = set()
    for entry in entries:
        if not isinstance(entry, Transaction):
            if isinstance(entry, Balance):
                commodities.add(entry.amount.currency)
            continue
        for posting in entry.postings:
            if posting.units is not None:
                commodities.add(posting.units.currency)
            if posting.cost is not None:
                commodities.add(posting.cost.currency)
            if posting.price is not None:
                commodities.add(posting.price.currency)
    return commodities


def metadata_required_for(account: str, requirements: dict[str, set[str]]) -> set[str]:
    required = set()
    for prefix, keys in requirements.items():
        if account == prefix or account.startswith(prefix + ":"):
            required.update(keys)
    return required


def included_bean_files(entrypoint: Path) -> set[Path]:
    """Return the complete local include closure rooted at a Beancount file."""

    pending = [entrypoint.resolve()]
    included = set()
    while pending:
        current = pending.pop()
        if current in included or not current.is_file():
            continue
        included.add(current)
        for line in current.read_text(encoding="utf-8").splitlines():
            match = INCLUDE_RE.match(line)
            if not match:
                continue
            pattern = Path(match.group(1))
            if pattern.is_absolute():
                matches = [pattern] if pattern.is_file() else []
            else:
                matches = current.parent.glob(str(pattern))
            pending.extend(path.resolve() for path in matches if path.is_file())
    return included


def unreferenced_bean_files(root: Path, ledger: Path) -> list[str]:
    """Find managed ledger files that cannot be reached from main.bean."""

    reachable = included_bean_files(ledger)
    managed = {path.resolve() for path in root.rglob("*.bean")}
    return sorted(str(path.relative_to(root.resolve())) for path in managed - reachable)


def unknown_config_accounts(opens: set[str], config: Path | None = None) -> list[str]:
    """Find non-placeholder Fane account references without an open directive."""
    if config is None or not config.is_file():
        return []

    import yaml

    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Fane config must be a YAML object")
    # Ledger policy keys are account prefixes, not posting references.
    conversion = {key: value for key, value in data.items() if key != "ledger"}
    references = set(ACCOUNT_REFERENCE_RE.findall(yaml.safe_dump(conversion)))
    return sorted(
        account for account in references - opens if not account.endswith(":FIXME")
    )


def validate_ledger(
    ledger: Path, policy: Policy, config: Path | None = None, allowed_accounts=()
) -> list[str]:
    entries, errors, options = loader.load_file(str(ledger))
    failures = []

    if errors:
        failures.append(f"Beancount loader returned {len(errors)} error(s).")
        failures.extend(str(error) for error in errors[:20])

    unreferenced_files = unreferenced_bean_files(ledger.parent, ledger)
    if unreferenced_files:
        failures.append("Managed .bean files not reachable from main.bean:")
        failures.extend(f"  - {path}" for path in unreferenced_files)

    opens = {entry.account: entry for entry in entries if isinstance(entry, Open)}
    first_usage = used_accounts(entries)

    unknown_fane_accounts = unknown_config_accounts(set(opens), config=config)
    if unknown_fane_accounts:
        failures.append("Fane config references accounts without open directives:")
        failures.extend(f"  - {account}" for account in unknown_fane_accounts)

    unused_opens = unused_open_accounts(opens, first_usage)
    if unused_opens:
        failures.append("Open accounts without any ledger reference:")
        failures.extend(f"  - {account}" for account in unused_opens)

    allowed_ambiguous_accounts = set(allowed_accounts) | policy.allowed_accounts
    ambiguous_accounts = ambiguous_account_segments(
        opens,
        allowed_accounts=allowed_ambiguous_accounts,
        disallowed_segments=policy.disallowed_segments,
    )
    if ambiguous_accounts:
        failures.append("Accounts contain ambiguous segments:")
        for account, segments in ambiguous_accounts.items():
            failures.append(f"  - {account}: {', '.join(segments)}")

    missing_opens = sorted(set(first_usage) - set(opens))
    if missing_opens:
        failures.append("Used accounts without explicit open directives:")
        failures.extend(f"  - {account}" for account in missing_opens)

    late_opens = []
    for account, first_entry in first_usage.items():
        open_entry = opens.get(account)
        if open_entry and open_entry.date > first_entry.date:
            late_opens.append((account, open_entry.date, first_entry.date))
    if late_opens:
        failures.append("Accounts opened after their first usage:")
        failures.extend(
            f"  - {account}: open {open_date}, first use {first_date}"
            for account, open_date, first_date in late_opens
        )

    operating_currencies = set(options.get("operating_currency", []))
    missing_required = sorted(policy.required_currencies - operating_currencies)
    if missing_required:
        failures.append(
            "Missing required operating currencies: " + ", ".join(missing_required)
        )

    unreported_commodities = sorted(commodities_used(entries) - operating_currencies)
    if unreported_commodities:
        failures.append(
            "Commodities used but not configured as operating currencies: "
            + ", ".join(unreported_commodities)
        )

    metadata_failures = defaultdict(list)
    for account, open_entry in sorted(opens.items()):
        required = metadata_required_for(account, policy.required_metadata)
        missing = sorted(required - set(open_entry.meta))
        if missing:
            metadata_failures[account].extend(missing)
    if metadata_failures:
        failures.append("Accounts missing required metadata:")
        for account, missing in metadata_failures.items():
            failures.append(f"  - {account}: {', '.join(missing)}")

    return failures
