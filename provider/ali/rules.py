from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field


@dataclass
class Rule(BaseModel):
    peer: Optional[str] = Field(default=None, description="交易对方")
    note: Optional[str] = Field(default=None, description="备注")
    item: Optional[str] = Field(default=None, description="商品说明")
    category: Optional[str] = Field(default=None, description="商品分类")
    type: Optional[str] = Field(default=None, description="交易类型")
    method: Optional[str] = Field(default=None, description="交易方式（账户）")
    status: Optional[str] = Field(default=None, description="交易状态")
    separator: Optional[str] = Field(default=None, description="分割符")
    time: Optional[str] = Field(default=None, description="交易时间段")
    timestamp_range: Optional[str] = Field(
        alias="timestamp-range", default=None, description="交易时间戳段"
    )
    method_account: Optional[str] = Field(
        alias="method-account", default=None, description="beancount的负向账户"
    )
    target_account: Optional[str] = Field(
        alias="target-account", default=None, description="beancount正向账户"
    )
    pnl_account: Optional[str] = Field(
        alias="pnl-account", default=None, description="beancount收益账户"
    )
    full_match: Optional[bool] = Field(
        alias="full-match", default=None, description="是否全匹配"
    )
    tags: Optional[str] = Field(default=None, description="标签")
    ignore: Optional[bool] = Field(default=None, description="是否忽略当前交易")
    min_price: Optional[float] = Field(
        alias="min-price",
        default=None,
        description="交易最小金额(用来根据金额判断账户)",
    )
    max_price: Optional[float] = Field(
        alias="max-price",
        default=None,
        description="交易最大金额(用来根据金额判断账户)",
    )


@dataclass
class ALi:
    rules: Optional[list[Rule]] = Field(default=None)
