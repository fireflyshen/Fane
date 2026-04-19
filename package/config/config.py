from pydantic import BaseModel, Field
from provider.ali.rules import ALi
from provider.wechat.rules import WeChat
from typing import Optional


class Config(BaseModel):
    title: Optional[str] = Field(alias="title", default=None)
    default_minus_account: Optional[str] = Field(
        alias="default-minus-account", default=None
    )
    default_plus_account: Optional[str] = Field(
        alias="default-plus-account", default=None
    )
    default_cash_account: Optional[str] = Field(
        alias="default-cash-account", default=None
    )
    default_position_account: Optional[str] = Field(
        alias="default-position-account", default=None
    )
    default_commission_account: Optional[str] = Field(
        alias="default-commission-account", default=None
    )
    default_pnl_account: Optional[str] = Field(
        alias="default-pnl-account", default=None
    )
    default_third_party_custody_account: Optional[str] = Field(
        alias="default-third-party-custody-account", default=None
    )
    default_currency: Optional[str] = Field(alias="default-currency", default=None)
    ali: Optional[ALi] = Field(alias="alipay", default=None)
    wechat: Optional[WeChat] = Field(alias="wechat", default=None)
