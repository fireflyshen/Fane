from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Optional, Protocol

from ir.ir import Order, Type
from package.errors import ConfigError
from package.parser.utils.utils import split_find_contains

ExtraAccounts = dict[str, str]
AccountResolutionTuple = tuple[
    bool, Optional[str], Optional[str], ExtraAccounts, list[str]
]
RANGE_SEPARATORS = ("..", "~", " - ", ",")
DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")


class RuleLike(Protocol):
    separator: Optional[str]
    ignore: Optional[bool]
    target_account: Optional[str]
    method_account: Optional[str]
    tags: Optional[str]
    time: Optional[str]
    timestamp_range: Optional[str]
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]


@dataclass(frozen=True)
class AccountResult:
    ignore: bool
    minus_account: Optional[str]
    plus_account: Optional[str]
    extra_account: ExtraAccounts
    tags: list[str]

    def as_tuple(self) -> AccountResolutionTuple:
        return (
            self.ignore,
            self.minus_account,
            self.plus_account,
            self.extra_account,
            self.tags,
        )


@dataclass(frozen=True)
class MatchField:
    rule_attr: str
    order_attr: str


@dataclass(frozen=True)
class ExtraAccountField:
    rule_attr: str
    account_key: str


class RuleAccountResolver:
    def __init__(
        self,
        match_fields: Iterable[MatchField],
        extra_account_fields: Iterable[ExtraAccountField] = (),
    ):
        self.match_fields = tuple(match_fields)
        self.extra_account_fields = tuple(extra_account_fields)

    def resolve(
        self,
        order: Order,
        rules: Iterable[RuleLike],
        default_minus_account: Optional[str],
        default_plus_account: Optional[str],
    ) -> AccountResult:
        ignore = False
        minus_account = default_minus_account
        plus_account = default_plus_account
        extra_account: ExtraAccounts = {}
        tags: list[str] = []

        for rule in rules:
            match = self._matches_rule(rule, order)
            separator = self._separator(rule)

            if match:
                if rule.ignore:
                    ignore = True
                    break
                minus_account, plus_account = self._resolve_accounts(
                    order, rule, minus_account, plus_account
                )
                extra_account = self._resolve_extra_account(rule, extra_account)
                if rule.tags is not None:
                    tags = rule.tags.split(separator)

            if match and self._is_refund(order):
                return AccountResult(
                    ignore, plus_account, minus_account, extra_account, tags
                )

        if self._is_refund(order):
            return AccountResult(ignore, plus_account, minus_account, extra_account, tags)

        return AccountResult(ignore, minus_account, plus_account, extra_account, tags)

    def _matches_rule(self, rule: RuleLike, order: Order) -> bool:
        match = True
        separator = self._separator(rule)
        for field in self.match_fields:
            rule_value = getattr(rule, field.rule_attr)
            if rule_value is not None:
                order_value = getattr(order, field.order_attr)
                match = split_find_contains(rule_value, order_value, separator, match)
                if not match:
                    return False
        match = self._matches_amount_range(rule, order, match)
        if not match:
            return False
        return self._matches_time_range(rule, order, match)

    def _matches_amount_range(
        self, rule: RuleLike, order: Order, match: bool
    ) -> bool:
        if rule.min_price is None and rule.max_price is None:
            return match
        if rule.min_price is not None and rule.max_price is not None:
            if rule.min_price > rule.max_price:
                raise ConfigError(
                    f"金额区间配置错误: min-price {rule.min_price} "
                    f"大于 max-price {rule.max_price}"
                )
        if rule.min_price is not None and order.money < rule.min_price:
            return False
        if rule.max_price is not None and order.money > rule.max_price:
            return False
        return match

    def _matches_time_range(
        self, rule: RuleLike, order: Order, match: bool
    ) -> bool:
        if rule.time is None and rule.timestamp_range is None:
            return match
        if order.pay_time is None:
            return False
        if rule.timestamp_range is not None:
            start, end = self._parse_datetime_range(rule.timestamp_range)
            if start is not None and order.pay_time < start:
                return False
            if end is not None and order.pay_time > end:
                return False
        if rule.time is not None:
            start_time, end_time = self._parse_clock_time_range(rule.time)
            if not self._clock_time_in_range(
                order.pay_time.time(), start_time, end_time
            ):
                return False
        return match

    def _parse_datetime_range(
        self, value: str
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        start_text, end_text = self._split_range(value, "timestamp-range")
        start = self._parse_datetime_bound(start_text, is_end=False)
        end = self._parse_datetime_bound(end_text, is_end=True)
        if start is not None and end is not None and start > end:
            raise ConfigError(f"时间区间配置错误: {value}")
        return start, end

    def _parse_clock_time_range(self, value: str) -> tuple[time, time]:
        start_text, end_text = self._split_range(value, "time")
        if start_text == "" or end_text == "":
            raise ConfigError(f"time 必须同时配置开始和结束时间: {value}")
        return (
            self._parse_clock_time(start_text),
            self._parse_clock_time(end_text),
        )

    def _split_range(self, value: str, field_name: str) -> tuple[str, str]:
        text = value.strip()
        for separator in RANGE_SEPARATORS:
            if separator in text:
                start, end = text.split(separator, 1)
                return start.strip(), end.strip()
        raise ConfigError(
            f"{field_name} 区间格式错误: {value}。"
            "请使用 start..end，例如 2026-06-01..2026-06-30 或 09:00..18:00"
        )

    def _parse_datetime_bound(
        self, value: str, *, is_end: bool
    ) -> Optional[datetime]:
        if value == "":
            return None
        for fmt in DATETIME_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            if fmt == "%Y-%m-%d" and is_end:
                return parsed.replace(hour=23, minute=59, second=59)
            return parsed
        raise ConfigError(
            f"timestamp-range 时间格式错误: {value}。"
            "支持 YYYY-MM-DD、YYYY-MM-DD HH:MM、YYYY-MM-DD HH:MM:SS"
        )

    def _parse_clock_time(self, value: str) -> time:
        for fmt in TIME_FORMATS:
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
        raise ConfigError(f"time 时间格式错误: {value}。支持 HH:MM 或 HH:MM:SS")

    def _clock_time_in_range(self, current: time, start: time, end: time) -> bool:
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    def _separator(self, rule: RuleLike) -> str:
        if rule.separator is not None:
            return rule.separator
        return ","

    def _resolve_accounts(
        self,
        order: Order,
        rule: RuleLike,
        minus_account: Optional[str],
        plus_account: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if rule.target_account is not None:
            if order.type == Type.RECV:
                minus_account = rule.target_account
            else:
                plus_account = rule.target_account
        if rule.method_account is not None:
            if order.type == Type.RECV:
                plus_account = rule.method_account
            else:
                minus_account = rule.method_account
        return minus_account, plus_account

    def _resolve_extra_account(
        self, rule: RuleLike, extra_account: ExtraAccounts
    ) -> ExtraAccounts:
        for field in self.extra_account_fields:
            account = getattr(rule, field.rule_attr)
            if account is not None:
                extra_account = {field.account_key: str(account)}
        return extra_account

    def _is_refund(self, order: Order) -> bool:
        return order.item.startswith("退款")
