"""Read the legacy repayment balance, preserving posting/include semantics."""

import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

from fane.shared.errors import ProviderError

POSTING_PATTERN_TEMPLATE = (
    r"^\s+{account}\s+([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)"
    r"\s+([A-Z][A-Z0-9._'-]*)\b"
)
BALANCE_PATTERN_TEMPLATE = (
    r"^\d{{4}}-\d{{2}}-\d{{2}}\s+balance\s+{account}\s+"
    r"([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)\s+([A-Z][A-Z0-9._'-]*)\b"
)
INCLUDE_PATTERN = re.compile(r'^\s*include\s+"([^"]+)"')


def read_account_balance(ledger_file: str, account: str, currency: str) -> Decimal:
    ledger_path = Path(ledger_file).expanduser()
    if not ledger_path.is_file():
        raise ProviderError(f"外币信用卡账本文件不存在: {ledger_file}")

    posting_pattern = re.compile(
        POSTING_PATTERN_TEMPLATE.format(account=re.escape(account))
    )
    balance_pattern = re.compile(
        BALANCE_PATTERN_TEMPLATE.format(account=re.escape(account))
    )
    balance = Decimal("0")
    for line in iter_ledger_lines(ledger_path):
        balance_match = balance_pattern.match(line)
        if balance_match:
            amount, posting_currency = balance_match.groups()
            if posting_currency == currency:
                balance = Decimal(amount.replace(",", ""))
            continue

        match = posting_pattern.match(line)
        if not match:
            continue
        amount, posting_currency = match.groups()
        if posting_currency != currency:
            continue
        balance += Decimal(amount.replace(",", ""))

    return balance


def iter_ledger_lines(
    ledger_path: Path, visited: set[Path] | None = None
) -> Iterator[str]:
    visited = visited or set()
    resolved_path = ledger_path.expanduser().resolve()
    if resolved_path in visited:
        return
    visited.add(resolved_path)

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            for line in f:
                include_match = INCLUDE_PATTERN.match(line)
                if include_match:
                    include_path = resolved_path.parent / include_match.group(1)
                    yield from iter_ledger_lines(include_path, visited)
                yield line
    except OSError as e:
        raise ProviderError(f"读取外币信用卡账本失败: {resolved_path}") from e
