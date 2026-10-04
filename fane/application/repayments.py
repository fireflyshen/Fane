from decimal import Decimal

from fane.config import Config, ForeignCreditCardRepayment
from fane.core.models import IR, Order
from fane.infrastructure.ledger.balance import iter_ledger_lines as iter_ledger_lines
from fane.infrastructure.ledger.balance import read_account_balance


def post_process(ir: IR, config: Config | None = None) -> IR:
    orders: list[Order] = []
    used_repayment_rules: set[int] = set()

    for o in ir.orders:
        meta = o.meta_data or {}
        status = meta.get("status")
        money = o.money or Decimal("0.0")

        if status == "交易关闭" and meta.get("type") == "不计收支":
            continue

        if status == "等待确认收货" and money == Decimal("0.0"):
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
