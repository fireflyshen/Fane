from pathlib import Path

from fane.shared.models import Account, Order
from fane.shared.render.templates import (
    NormalOrder,
    render_normal_order,
)


class NormalStrategy:
    def __init__(self, template_file: Path | None = None) -> None:
        self.template_file = template_file

    def render_order(self, order: Order) -> tuple[str, str]:
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
        data = render_normal_order(
            normal_order,
            template_name=f"{order.order_type.value}.j2",
            template_file=self.template_file,
        )

        if "收益发放" in normal_order.item:
            return "income", data
        return "expense", data
