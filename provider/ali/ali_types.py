from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class DealType(Enum):
    SEND = "支出"
    RECV = "收入"
    OTHERS = "不计收支"
    EMPTY = ""
    NIL = "未知"


class DealStatus(Enum):
    SUCCESS = "交易成功"
    CLOSE = "交易关闭"
    REPAY = "还款成功"
    SHOP_PENDING = "等待确认收货"


@dataclass
class AliOrder:
    type: DealType
    type_original: str
    peer: str
    peer_account: str
    item_name: str
    method: str
    money: Decimal
    status: DealStatus
    category: str
    deal_no: str
    merchant_id: str
    pay_time: datetime
    target_account: str
    method_account: str
    notes: str
