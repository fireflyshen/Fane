from pathlib import Path

from jinja2 import Template
from jinja2.exceptions import TemplateError as JinjaError

from fane.core.errors import TemplateError
from fane.core.models import Account, Order
from fane.infrastructure.rendering.strategy import TemplateStrategy
from fane.infrastructure.rendering.templates import NormalOrder, get_template


class NormalStrategy(TemplateStrategy):
    def __init__(self, template_file: Path | None = None) -> None:
        self.template_file = template_file
        self.expense_list: list[str] = []
        self.income_list: list[str] = []

    @classmethod
    def get_template_content(cls, template_name: str) -> Template:
        return get_template(template_name)

    def render_order(self, order: Order) -> tuple[str, str]:
        template = get_template(f"{order.order_type.value}.j2", self.template_file)
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
        try:
            data = template.render(**vars(normal_order))
        except JinjaError as error:
            raise TemplateError(
                f"模板渲染失败: {error}；可用变量见 fa template fields"
            ) from error

        if "收益发放" in normal_order.item:
            return "income", data
        return "expense", data

    def template_parser(self, order: Order) -> None:
        kind, data = self.render_order(order)
        if kind == "income":
            self.income_list.append(data)
        else:
            self.expense_list.append(data)
