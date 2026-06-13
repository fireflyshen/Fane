from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional

from ir.ir import Order, Type
from package.parser.utils.utils import split_find_contains


@dataclass(frozen=True)
class AccountResult:
    ignore: bool
    minus_account: Optional[str]
    plus_account: Optional[str]
    extra_account: dict
    tags: list[str]

    def as_tuple(self) -> tuple:
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
    account_key: Any


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
        rules: Iterable[Any],
        default_minus_account: Optional[str],
        default_plus_account: Optional[str],
    ) -> AccountResult:
        ignore = False
        minus_account = default_minus_account
        plus_account = default_plus_account
        extra_account = {}
        tags = []

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

    def _matches_rule(self, rule: Any, order: Order) -> bool:
        match = True
        separator = self._separator(rule)
        for field in self.match_fields:
            rule_value = getattr(rule, field.rule_attr)
            if rule_value is not None:
                order_value = getattr(order, field.order_attr)
                match = split_find_contains(rule_value, order_value, separator, match)
        return match

    def _separator(self, rule: Any) -> str:
        if rule.separator is not None:
            return rule.separator
        return ","

    def _resolve_accounts(
        self,
        order: Order,
        rule: Any,
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

    def _resolve_extra_account(self, rule: Any, extra_account: dict) -> dict:
        for field in self.extra_account_fields:
            account = getattr(rule, field.rule_attr)
            if account is not None:
                extra_account = {field.account_key: account}
        return extra_account

    def _is_refund(self, order: Order) -> bool:
        return str.startswith(order.item, "退款")
