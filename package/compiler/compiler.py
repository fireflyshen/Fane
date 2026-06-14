import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Pattern

from ir.ir import IR, Order
from package.compiler.post_processors import apply_post_processor
from package.compiler.results import RenderedEntry, fingerprint_order
from package.config import Config
from package.parser.analyser import Analyser
from package.strategy.template.strategy import TemplateStrategy
from package.strategy.template.normal import NormalStrategy

MONTH_PATTERN: Pattern[str] = re.compile(r"^\d{4}-(\d{2})-\d{2}")
CompiledResult = dict[str, dict[str, list[str]]]


class Compiler:
    def __init__(
        self,
        provider: str,
        config: Config,
        ir: IR,
        template_strategy: TemplateStrategy,
        analyser: Analyser,
    ):
        self.provider = provider
        self.privider = provider
        self.config = config
        self.ir = ir
        self.template_strategy = template_strategy
        self.analyser = analyser
        self.source_file = ""

    def compile(self) -> None:
        logging.debug("start compile")
        data_str = json.dumps(self.build_result(), ensure_ascii=False)
        print(data_str)

    def build_result(self) -> CompiledResult:
        self.prepare_ir()
        self.render_orders(self.ir.orders or [])

        expense_data = self.distribution(self.template_strategy.expense_list)
        income_data = self.distribution(self.template_strategy.income_list)

        return {
            "expense": {k: sorted(v) for k, v in sorted(expense_data.items())},
            "income": {k: sorted(v) for k, v in sorted(income_data.items())},
        }

    def prepare_ir(self) -> IR:
        self.ir.orders = self.resolve_accounts(self.ir.orders or [])
        self.ir = apply_post_processor(self.provider, self.ir, self.config)
        return self.ir

    def build_entries(self, source_file: str = "") -> list[RenderedEntry]:
        self.source_file = source_file
        self.prepare_ir()
        entries: list[RenderedEntry] = []
        renderer = self.template_strategy
        for order in self.ir.orders or []:
            if not isinstance(renderer, NormalStrategy):
                self.template_strategy.template_parser(order)
                continue
            kind, content = renderer.render_order(order)
            entry_date = (
                order.pay_time.date() if order.pay_time else self._entry_date(content)
            )
            entries.append(
                RenderedEntry(
                    date=entry_date,
                    month=f"{entry_date.month:02d}",
                    kind=kind,
                    fingerprint=fingerprint_order(self.provider, order),
                    content=content,
                    source_provider=self.provider,
                    source_file=source_file,
                    order_id=order.order_id or order.meta_data.get("order_id") or None,
                )
            )
        return entries

    def resolve_accounts(self, source_orders: Iterable[Order]) -> list[Order]:
        orders: list[Order] = []
        for o in source_orders:
            ignore, res_minus, res_plus, extra_account, tags = (
                self.analyser.get_account_and_tags(o, self.config)
            )
            if ignore:
                continue
            o.minus_account = res_minus
            o.plus_account = res_plus
            o.extra_account = extra_account
            o.tags = tags
            orders.append(o)
        return orders

    def apply_accounts(self) -> None:
        self.ir.orders = self.resolve_accounts(self.ir.orders or [])

    def apply_provider_post_process(self) -> None:
        self.ir = apply_post_processor(self.provider, self.ir, self.config)

    def render_orders(self, orders: Iterable[Order] | None = None) -> None:
        for io in orders if orders is not None else self.ir.orders or []:
            self.template_strategy.template_parser(io)

    def distribution(self, bean_bill_list: list[str]) -> dict[str, list[str]]:
        monthly_data: defaultdict[str, list[str]] = defaultdict(list)

        for item in bean_bill_list:
            match_obj = MONTH_PATTERN.match(item)
            if match_obj:
                month = match_obj.group(1)
                monthly_data[month].append(item)
        return dict(monthly_data)

    def _entry_date(self, content: str):
        from datetime import datetime

        match_obj = MONTH_PATTERN.match(content)
        if match_obj:
            return datetime.strptime(content[:10], "%Y-%m-%d").date()
        raise ValueError("无法从渲染结果中解析交易日期")
