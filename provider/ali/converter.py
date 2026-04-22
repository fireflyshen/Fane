from ir.ir import IR, Order, Type
from provider.ali.ali_types import AliOrder, DealType


def get_private_meta_data(ali_order: AliOrder) -> dict:
    source = "ALiPay"
    d = {}
    if source:
        d["source"] = source
    if ali_order.pay_time:
        d["pay_time"] = (
            ali_order.pay_time.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(ali_order.pay_time, "strftime")
            else str(ali_order.pay_time)
        )
    if ali_order.deal_no:
        d["deal_no"] = ali_order.deal_no
        d["order_id"] = ali_order.deal_no
    if ali_order.merchant_id:
        d["merchant_id"] = ali_order.merchant_id
    if ali_order.category:
        d["category"] = ali_order.category
    if ali_order.type_original:
        d["type"] = ali_order.type_original
    if ali_order.method:
        d["method"] = ali_order.method
    if ali_order.status:
        d["status"] = ali_order.status.value

    return d


def get_public_meta_data(ali_order: AliOrder) -> Order:
    return Order(
        peer=ali_order.peer,
        item=ali_order.item_name,
        category=ali_order.category,
        method=ali_order.method,
        pay_time=ali_order.pay_time,
        money=ali_order.money,
        order_id=ali_order.deal_no,
        type=convert_type(ali_order.type),
        type_original=ali_order.type_original,
        note=ali_order.notes,
        merchant_order_id=ali_order.merchant_id if ali_order.merchant_id else None,
    )


def config_meta_data(ali_order: AliOrder) -> Order:
    ir_order = get_public_meta_data(ali_order)
    ir_order.meta_data = get_private_meta_data(ali_order)
    return ir_order


def convert_type(type: DealType):
    type_dict: dict[DealType, Type] = {
        DealType.SEND: Type.SEND,
        DealType.RECV: Type.RECV,
        DealType.NIL: Type.UNKNOW,
        DealType.OTHERS: Type.UNKNOW,
        DealType.EMPTY: Type.UNKNOW,
    }

    return type_dict.get(type, Type.UNKNOW)


def convert_to_ir(ali_orders: list[AliOrder]):
    ir = IR()
    for ali_order in ali_orders:
        ir_order = config_meta_data(ali_order)
        ir.orders.append(ir_order)

    return ir
