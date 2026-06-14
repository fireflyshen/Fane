import hashlib
from dataclasses import dataclass
from datetime import date

from ir.ir import Order


@dataclass(frozen=True)
class RenderedEntry:
    date: date
    month: str
    kind: str
    fingerprint: str
    content: str
    source_provider: str
    source_file: str
    order_id: str | None = None


def fingerprint_order(provider: str, order: Order) -> str:
    order_id = order.order_id or order.meta_data.get("order_id")
    if order_id:
        return f"{provider}:{order_id}"

    merchant_order_id = order.merchant_order_id or order.meta_data.get("merchant_id")
    if merchant_order_id:
        return f"{provider}:merchant:{merchant_order_id}"

    fallback = "|".join(
        [
            provider,
            order.pay_time.isoformat() if order.pay_time else "",
            str(order.money),
            order.peer or "",
            order.item,
            order.method,
            order.type_original,
        ]
    )
    return f"{provider}:sha256:{hashlib.sha256(fallback.encode()).hexdigest()}"
