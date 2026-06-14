# 定义中间值
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import Field
from pydantic.dataclasses import dataclass


class OrderType(Enum):
    NORMAL = "normal"


class Type(Enum):
    SEND = "支"
    RECV = "收"
    UNKNOW = "未知"


class Account(Enum):
    cash_account = "cash_account"
    position_account = "position_account"
    commission_account = "commission_account"
    pnl_account = "pnl_account"
    third_party_custody_account = "third_party_custody_account"
    plus_account = "plus_account"
    minus_account = "minus_account"


@dataclass
class Order:
    order_type: OrderType = Field(
        default=OrderType.NORMAL, description="订单类型"
    )
    peer: Optional[str] = Field(default=None, description="交易对手")
    item: str = Field(default="", description="商品名")
    category: str = Field(default="", description="分类")
    merchant_order_id: Optional[str] = Field(default="", description="商户订单号")
    order_id: str = Field(default="", description="内部订单号")
    money: Decimal = Field(default=Decimal("0.0"), description="金额")
    note: str = Field(default="", description="备注")
    pay_time: Optional[datetime] = Field(default=None, description="支付时间")
    type: Optional[Type] = Field(default=None, description="收支类型")
    type_original: str = Field(default="", description="原始类型字符串")
    tx_type_original: str = Field(default="", description="原始交易类型")
    method: str = Field(default="", description="支付方式")
    amount: Decimal = Field(default=Decimal("0.0"))
    price: Decimal = Field(default=Decimal("0.0"))
    currency: str = Field(default="CNY")
    commission: Decimal = Field(default=Decimal("0.0"), description="手续费")
    units: dict[str, Any] = Field(default_factory=dict)
    extra_account: dict[str, str] = Field(
        default_factory=dict, description="额外账户,盈亏账户"
    )
    minus_account: str = Field(default="", description="负向账户")
    plus_account: str = Field(default="", description="正向账户")
    minus_str: str = Field(
        default="", description="负向字符串，用来解决外币转换问题"
    )
    plus_str: str = Field(
        default="", description="正向字符串，用来解决外币转换问题"
    )
    meta_data: dict[str, str] = Field(
        default_factory=dict, description="元数据"
    )
    tags: list[str] = Field(default_factory=list, description="标签")


@dataclass
class IR:
    orders: list[Order] = Field(
        default_factory=list, description="放置同用类型的订单"
    )
