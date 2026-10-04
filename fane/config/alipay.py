from pydantic import BaseModel, Field

from .rules import RuleBase


class Rule(RuleBase):
    note: str | None = Field(default=None, description="备注")
    pnl_account: str | None = Field(
        alias="pnl-account", default=None, description="beancount收益账户"
    )


class ALi(BaseModel):
    rules: list[Rule] | None = Field(default=None)
