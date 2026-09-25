from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, BaseModel, ValidationError

from package.config.config import (
    Config,
    ForeignCreditCardRepayment,
    RoutingConfig,
    SourceConfig,
    SyncJob,
    ValidatorConfig,
)
from package.config.init import load_config
from package.errors import ConfigError
from provider.ali.rules import ALi
from provider.ali.rules import Rule as AliRule
from provider.registry import supported_provider_names
from provider.wechat.rules import Rule as WechatRule
from provider.wechat.rules import WeChat

ACCOUNT_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9-]*(?::[A-Z][A-Za-z0-9-]*)+$")
COMMON_RANGE_FIELDS = {
    "time",
    "day-range",
    "timestamp-range",
    "min-price",
    "min-amount",
    "max-price",
    "max-amount",
}
ACTIVE_MATCH_FIELDS = {
    "alipay": COMMON_RANGE_FIELDS
    | {"peer", "note", "item", "category", "type", "method"},
    "wechat": COMMON_RANGE_FIELDS | {"peer", "item", "category", "tx_type", "method"},
}
INACTIVE_COMPATIBILITY_FIELDS = {
    "alipay": {"status", "full-match"},
    "wechat": {"type", "status", "full-match", "pnl-account"},
}
ACCOUNT_FIELDS = {
    "default-minus-account",
    "default-plus-account",
    "default-cash-account",
    "default-position-account",
    "default-commission-account",
    "default-pnl-account",
    "default-third-party-custody-account",
}


@dataclass
class DiagnosticReport:
    config_path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _accepted_keys(model: type[BaseModel]) -> set[str]:
    result: set[str] = set()
    for name, model_field in model.model_fields.items():
        alias = model_field.validation_alias or model_field.alias
        if isinstance(alias, str):
            result.add(alias)
        elif isinstance(alias, AliasChoices):
            result.update(str(choice) for choice in alias.choices)
        else:
            result.add(name)
    return result


def _warn_unknown(
    report: DiagnosticReport,
    value: Any,
    model: type[BaseModel],
    location: str,
) -> None:
    if not isinstance(value, dict):
        return
    for key in sorted(set(value) - _accepted_keys(model), key=str):
        report.warnings.append(f"{location}.{key}: 未识别字段，运行时会忽略")


def _check_rule_list(
    report: DiagnosticReport,
    section: Any,
    rule_model: type[BaseModel],
    provider: str,
) -> None:
    if not isinstance(section, dict):
        return
    rules = section.get("rules")
    if rules is None:
        report.info.append(f"{provider}: 未配置规则，将使用默认账户")
        return
    if not isinstance(rules, list):
        return
    report.info.append(f"{provider}: {len(rules)} 条规则")
    for index, rule in enumerate(rules):
        location = f"{provider}.rules[{index}]"
        _warn_unknown(report, rule, rule_model, location)
        if not isinstance(rule, dict):
            continue
        active_fields = ACTIVE_MATCH_FIELDS[provider]
        if not (set(rule) & active_fields):
            report.warnings.append(f"{location}: 没有匹配条件，会匹配所有交易")
        for field_name in sorted(set(rule) & INACTIVE_COMPATIBILITY_FIELDS[provider]):
            report.warnings.append(
                f"{location}.{field_name}: 为兼容保留，但当前不参与规则解析"
            )
        minimum = rule.get("min-price", rule.get("min-amount"))
        maximum = rule.get("max-price", rule.get("max-amount"))
        try:
            if minimum is not None and maximum is not None:
                if Decimal(str(minimum)) > Decimal(str(maximum)):
                    report.errors.append(f"{location}: 最小金额不能大于最大金额")
        except Exception:
            # Pydantic reports the precise validation error below.
            pass


def _check_jobs(report: DiagnosticReport, jobs: Any) -> None:
    if jobs is None:
        report.info.append("sync: 未配置 jobs；trans/import 仍可正常使用")
        return
    if not isinstance(jobs, dict):
        return
    report.info.append(f"sync: {len(jobs)} 个任务")
    supported = set(supported_provider_names())
    for job_name, job in jobs.items():
        location = f"jobs.{job_name}"
        _warn_unknown(report, job, SyncJob, location)
        if not isinstance(job, dict):
            continue
        timezone = job.get("timezone", "Asia/Shanghai")
        try:
            ZoneInfo(str(timezone))
        except ZoneInfoNotFoundError:
            report.errors.append(f"{location}.timezone: 未知时区 {timezone}")
        _warn_unknown(report, job.get("routing"), RoutingConfig, f"{location}.routing")
        sources = job.get("sources")
        if isinstance(sources, list):
            for index, source in enumerate(sources):
                source_location = f"{location}.sources[{index}]"
                _warn_unknown(report, source, SourceConfig, source_location)
                if isinstance(source, dict):
                    provider = source.get("provider")
                    if provider and provider not in supported:
                        report.errors.append(
                            f"{source_location}.provider: 不支持 {provider!r}"
                        )
        validators = job.get("validators")
        if isinstance(validators, list):
            for index, validator in enumerate(validators):
                validator_location = f"{location}.validators[{index}]"
                _warn_unknown(report, validator, ValidatorConfig, validator_location)
                if isinstance(validator, dict) and validator.get("cwd"):
                    cwd = Path(str(validator["cwd"])).expanduser()
                    if not cwd.is_dir():
                        report.warnings.append(f"{validator_location}.cwd: 目录不存在")


def diagnose_config(config_path: str | Path) -> DiagnosticReport:
    path = Path(config_path)
    report = DiagnosticReport(config_path=path)
    try:
        raw = load_config(path)
    except ConfigError as error:
        report.errors.append(str(error))
        return report

    _warn_unknown(report, raw, Config, "config")
    _warn_unknown(report, raw.get("alipay"), ALi, "alipay")
    _warn_unknown(report, raw.get("wechat"), WeChat, "wechat")
    _check_rule_list(report, raw.get("alipay"), AliRule, "alipay")
    _check_rule_list(report, raw.get("wechat"), WechatRule, "wechat")
    _check_jobs(report, raw.get("jobs"))

    repayments = raw.get("foreign-credit-card-repayments")
    if isinstance(repayments, list):
        for index, repayment in enumerate(repayments):
            _warn_unknown(
                report,
                repayment,
                ForeignCreditCardRepayment,
                f"foreign-credit-card-repayments[{index}]",
            )
            if isinstance(repayment, dict):
                ledger = repayment.get("ledger-file")
                if ledger and not Path(str(ledger)).expanduser().is_file():
                    report.warnings.append(
                        f"foreign-credit-card-repayments[{index}].ledger-file: 文件不存在"
                    )

    for field_name in ("default-minus-account", "default-plus-account"):
        if not raw.get(field_name):
            report.warnings.append(
                f"config.{field_name}: 未配置，未匹配交易可能无法入账"
            )

    for field_name in ACCOUNT_FIELDS:
        account = raw.get(field_name)
        if account and not ACCOUNT_PATTERN.fullmatch(str(account)):
            report.warnings.append(
                f"config.{field_name}: 账户名格式可能不符合 Beancount"
            )

    currency = raw.get("default-currency")
    if not currency:
        report.warnings.append("config.default-currency: 未配置默认币种")
    elif not re.fullmatch(r"[A-Z][A-Z0-9_'.-]{0,23}", str(currency)):
        report.warnings.append("config.default-currency: 币种格式可能不符合 Beancount")

    try:
        Config.model_validate(raw)
    except ValidationError as error:
        for item in error.errors(include_url=False, include_input=False):
            location = ".".join(str(part) for part in item["loc"])
            report.errors.append(f"{location}: {item['msg']}")

    return report
