"""Resolve and render transactions using injected collaborators."""

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from .models import IR, Order
from .ports import AccountResolver, OrderRenderer, PostProcessor
from .results import RenderedEntry, fingerprint_order

CompiledResult = dict[str, dict[str, list[str]]]
MONTH_PATTERN = re.compile(r"^\d{4}-(\d{2})-\d{2}")


class Compiler:
    def __init__(
        self,
        provider: str,
        ir: IR,
        renderer: OrderRenderer,
        account_resolver: AccountResolver,
        post_processor: PostProcessor,
        *,
        default_minus_account: str | None = None,
        default_plus_account: str | None = None,
    ):
        self.provider = provider
        self.ir = ir
        self.renderer = renderer
        self.account_resolver = account_resolver
        self.post_processor = post_processor
        self.default_minus_account = default_minus_account
        self.default_plus_account = default_plus_account
        self._prepared = False

    def prepare_ir(self) -> IR:
        if not self._prepared:
            self.apply_accounts()
            self.apply_provider_post_process()
            self._prepared = True
        return self.ir

    def resolve_accounts(self, source_orders: Iterable[Order]) -> list[Order]:
        orders: list[Order] = []
        for order in source_orders:
            ignore, minus, plus, extra, tags = self.account_resolver(order)
            if ignore:
                continue
            order.minus_account = minus or ""
            order.plus_account = plus or ""
            order.extra_account = extra
            order.tags = tags
            orders.append(order)
        return orders

    def apply_accounts(self) -> None:
        self.ir.orders = self.resolve_accounts(self.ir.orders)

    def apply_provider_post_process(self) -> None:
        self.ir = self.post_processor(self.ir)

    def build_entries(self, source_file: str = "") -> list[RenderedEntry]:
        entries: list[RenderedEntry] = []
        for order in self.prepare_ir().orders:
            kind, content = self.renderer.render_order(order)
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

    def build_result(self) -> CompiledResult:
        return group_entries(self.build_entries())

    def unmatched_count(self) -> int:
        return sum(
            1
            for order in self.prepare_ir().orders
            if (
                self.default_minus_account
                and order.minus_account == self.default_minus_account
            )
            or (
                self.default_plus_account
                and order.plus_account == self.default_plus_account
            )
        )

    @staticmethod
    def distribution(bean_bill_list: list[str]) -> dict[str, list[str]]:
        monthly_data: defaultdict[str, list[str]] = defaultdict(list)
        for content in bean_bill_list:
            match = MONTH_PATTERN.match(content)
            if match:
                monthly_data[match.group(1)].append(content)
        return dict(monthly_data)

    @staticmethod
    def _entry_date(content: str) -> date:
        if MONTH_PATTERN.match(content):
            return date.fromisoformat(content[:10])
        raise ValueError("无法从渲染结果中解析交易日期")


def group_entries(entries: Iterable[RenderedEntry]) -> CompiledResult:
    result: CompiledResult = {"expense": {}, "income": {}}
    for entry in entries:
        result[entry.kind].setdefault(entry.month, []).append(entry.content)
    return {
        kind: {month: sorted(contents) for month, contents in sorted(months.items())}
        for kind, months in result.items()
    }
