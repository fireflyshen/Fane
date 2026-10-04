from pydantic import BaseModel, Field

from .rules import RuleBase


class Rule(RuleBase):
    tx_type: str | None = Field(default=None, description="腾讯类型")
    commission_account: str | None = Field(
        alias="pnl-account", default=None, description="beancount收益账户"
    )


class WeChat(BaseModel):
    rules: list[Rule] | None = Field(default=None)
