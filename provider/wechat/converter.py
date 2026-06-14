from ir.ir import IR, Order, Type
from provider.wechat.wechat_types import DealType, WechatOrder

TYPE_MAP: dict[DealType, Type] = {
    DealType.SEND: Type.SEND,
    DealType.RECV: Type.RECV,
    DealType.NIL: Type.UNKNOW,
}


def get_private_meta_data(wechat_order: WechatOrder) -> dict[str, str]:
    # 支付时间
    source = "WeChat"
    d: dict[str, str] = {}
    if source:
        d["source"] = source
    if wechat_order.pay_time:
        d["pay_time"] = (
            wechat_order.pay_time.strftime("%Y-%m-%d")
            if hasattr(wechat_order.pay_time, "strftime")
            else str(wechat_order.pay_time)
        )
    if wechat_order.mechant_order_id:
        d["merchant_id"] = wechat_order.mechant_order_id
    if wechat_order.tx_type_original:
        d["tx_type"] = wechat_order.tx_type_original
    if wechat_order.method:
        d["method"] = wechat_order.method
    if wechat_order.status:
        d["status"] = wechat_order.status
    if wechat_order.order_id:
        d["order_id"] = wechat_order.order_id
    if wechat_order.commision:
        d["commision"] = wechat_order.commision
    return d


def get_public_meta_data(wechat_order: WechatOrder) -> Order:
    return Order(
        peer=wechat_order.peer,
        item=wechat_order.item,
        method=wechat_order.method,
        pay_time=wechat_order.pay_time,
        money=wechat_order.money,
        order_id=wechat_order.order_id,
        type=convert_type(wechat_order.type),
        type_original=wechat_order.type_original,
        tx_type_original=wechat_order.tx_type_original,
        merchant_order_id=(
            wechat_order.mechant_order_id if wechat_order.mechant_order_id else None
        ),
    )


def config_meta_data(wechat_order: WechatOrder) -> Order:
    ir_order = get_public_meta_data(wechat_order)
    ir_order.meta_data = get_private_meta_data(wechat_order)
    return ir_order


def convert_type(deal_type: DealType) -> Type:
    return TYPE_MAP.get(deal_type, Type.UNKNOW)


def convert_to_ir(wechat_orders: list[WechatOrder]) -> IR:
    return IR(orders=[config_meta_data(wechat_order) for wechat_order in wechat_orders])
