import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

from ir.ir import IR, Order
from package.config import Config, ForeignCreditCardRepayment
from package.errors import ProviderError
from provider.ali.ali_types import DealStatus


POSTING_PATTERN_TEMPLATE = (
    r"^\s+{account}\s+([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)"
    r"\s+([A-Z][A-Z0-9._'-]*)\b"
)
INCLUDE_PATTERN = re.compile(r'^\s*include\s+"([^"]+)"')


def post_process(ir: IR, config: Config | None = None) -> IR:
    orders: list[Order] = []
    used_repayment_rules: set[int] = set()

    for o in ir.orders:
        meta = o.meta_data or {}
        status = meta.get("status")

        if status == DealStatus.CLOSE.value and meta.get("type") == "不计收支":
            continue

        if status == DealStatus.SHOP_PENDING.value:
            continue

        orders.append(o)
        repayment_order = foreign_credit_card_repayment_order(
            o, config, used_repayment_rules
        )
        if repayment_order is not None:
            orders.append(repayment_order)

    ir.orders = orders
    return ir


def foreign_credit_card_repayment_order(
    order: Order, config: Config | None, used_rules: set[int]
) -> Order | None:
    if config is None:
        return None

    rules = config.foreign_credit_card_repayments or []
    for index, rule in enumerate(rules):
        if index in used_rules:
            continue
        if not matches_repayment_rule(order, rule):
            continue

        foreign_money = get_repayment_amount(rule)
        if foreign_money <= 0:
            return None

        used_rules.add(index)
        return Order(
            pay_time=order.pay_time,
            peer=rule.peer or order.peer,
            item=rule.item or order.item,
            money=order.money,
            order_id=order.order_id,
            merchant_order_id=order.merchant_order_id,
            minus_account=order.plus_account,
            plus_account=rule.liability_account,
            minus_str=f"-{order.money} CNY",
            plus_str=f"{foreign_money} {rule.currency} @@ {order.money} CNY",
            currency="CNY",
            meta_data=order.meta_data,
            tags=order.tags,
        )

    return None


def matches_repayment_rule(order: Order, rule: ForeignCreditCardRepayment) -> bool:
    if rule.trigger_minus_account and order.minus_account != rule.trigger_minus_account:
        return False
    if rule.trigger_plus_account and order.plus_account != rule.trigger_plus_account:
        return False
    return bool(rule.trigger_minus_account or rule.trigger_plus_account)


def get_repayment_amount(rule: ForeignCreditCardRepayment) -> Decimal:
    balance = read_account_balance(
        rule.ledger_file, rule.liability_account, rule.currency
    )
    if balance < 0:
        return -balance
    return balance


def read_account_balance(ledger_file: str, account: str, currency: str) -> Decimal:
    ledger_path = Path(ledger_file).expanduser()
    if not ledger_path.is_file():
        raise ProviderError(f"外币信用卡账本文件不存在: {ledger_file}")

    pattern = re.compile(POSTING_PATTERN_TEMPLATE.format(account=re.escape(account)))
    balance = Decimal("0")
    for line in iter_ledger_lines(ledger_path):
        match = pattern.match(line)
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
