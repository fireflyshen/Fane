from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from provider.ali.rules import ALi
from provider.wechat.rules import WeChat


class ForeignCreditCardRepayment(BaseModel):
    trigger_minus_account: Optional[str] = Field(
        alias="trigger-minus-account", default=None
    )
    trigger_plus_account: Optional[str] = Field(
        alias="trigger-plus-account", default=None
    )
    liability_account: str = Field(alias="liability-account")
    ledger_file: str = Field(alias="ledger-file")
    currency: str = Field(default="USD")
    peer: Optional[str] = Field(default=None)
    item: Optional[str] = Field(default=None)


class ValidatorConfig(BaseModel):
    command: list[str]
    cwd: Optional[str] = None
    timeout_seconds: int = Field(alias="timeout-seconds", default=300, gt=0)

    @model_validator(mode="after")
    def command_must_not_be_empty(self) -> "ValidatorConfig":
        if not self.command:
            raise ValueError("validator command must not be empty")
        return self


class RoutingConfig(BaseModel):
    expense: str = "{year}/{year}-{month}.bean"
    income: str = "{year}/income.bean"


class SourceConfig(BaseModel):
    id: str
    provider: str
    path: Optional[str] = None
    glob: Optional[str] = None
    on_missing: Optional[Literal["skip", "error"]] = Field(
        alias="on-missing", default=None
    )

    @model_validator(mode="after")
    def exactly_one_location(self) -> "SourceConfig":
        if (self.path is None) == (self.glob is None):
            raise ValueError("exactly one of path or glob is required")
        return self


class SyncJob(BaseModel):
    timezone: str = "Asia/Shanghai"
    journal_dir: str = Field(alias="journal-dir")
    state_file: Optional[str] = Field(alias="state-file", default=None)
    lock_file: Optional[str] = Field(alias="lock-file", default=None)
    dedupe_index: Optional[str] = Field(alias="dedupe-index", default=None)
    on_missing: Literal["skip", "error"] = Field(alias="on-missing", default="skip")
    require_classified: bool = Field(alias="require-classified", default=False)
    change_detection: Literal["sha256", "none"] = Field(
        alias="change-detection", default="sha256"
    )
    write_mode: Literal["append"] = Field(alias="write-mode", default="append")
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    sources: list[SourceConfig]
    validators: list[ValidatorConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_ids_must_be_unique(self) -> "SyncJob":
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique within a job")
        return self


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
    foreign_credit_card_repayments: Optional[list[ForeignCreditCardRepayment]] = Field(
        alias="foreign-credit-card-repayments", default=None
    )
    jobs: Optional[dict[str, SyncJob]] = None
