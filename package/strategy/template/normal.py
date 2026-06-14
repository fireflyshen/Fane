from functools import lru_cache

from jinja2 import Template

from ir.ir import Order, Account
from package.strategy.template.strategy import TemplateStrategy
from package.template.template import NormalOrder
from package.template.template import get_template


class NormalStrategy(TemplateStrategy):

    def __init__(self) -> None:
        self.expense_list: list[str] = []
        self.income_list: list[str] = []

    @classmethod
    @lru_cache(maxsize=5)
    def get_template_content(cls, template_name: str) -> Template:
        return get_template(template_name)

    def render_order(self, order: Order) -> tuple[str, str]:
        template = self.get_template_content(f"{order.order_type.value}.j2")
        normal_order = NormalOrder(
            pay_time=order.pay_time,
            peer=order.peer,
            item=order.item,
            note=order.note,
            money=order.money,
            commission=order.commission,
            minus_account=order.minus_account,
            plus_account=order.plus_account,
            plus_str=order.plus_str,
            minus_str=order.minus_str,
            pnl_account=order.extra_account.get(Account.pnl_account.value, ""),
            commission_account=order.extra_account.get(
                Account.commission_account.value, ""
            ),
            currency=order.currency,
            metadata=order.meta_data,
            tags=order.tags,
        )
        data = template.render(**vars(normal_order))

        if "收益发放" in normal_order.item:
            return "income", data
        return "expense", data

    def template_parser(self, order: Order) -> None:
        kind, data = self.render_order(order)
        if kind == "income":
            self.income_list.append(data)
        else:
            self.expense_list.append(data)
