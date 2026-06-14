from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class DealType(Enum):
    SEND = "支出"
    RECV = "收入"
    NIL = "/"


class TxType(Enum):
    tx_type_consume = "商户消费"
    tx_type_credit = "信用卡还款"
    tx_type_transfer = "转账"
    tx_type_hongbao = "微信红包"


@dataclass
class WechatOrder:
    order_id: str
    mechant_order_id: str
    pay_time: datetime
    type: DealType
    type_original: str
    peer: str
    item: str
    money: Decimal
    tx_type: TxType
    tx_type_original: str
    status: str
    method: str
    commision: str
