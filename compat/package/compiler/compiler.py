"""Compatibility adapter for the historical Compiler constructor and stdout API."""

import json

from fane.shared.compiler import MONTH_PATTERN as MONTH_PATTERN
from fane.shared.compiler import CompiledResult as CompiledResult
from fane.shared.compiler import Compiler as CoreCompiler
from package.compiler.post_processors import apply_post_processor


class _LegacyRenderer:
    def __init__(self, strategy):
        self.strategy = strategy

    def render_order(self, order):
        if callable(getattr(self.strategy, "render_order", None)):
            return self.strategy.render_order(order)
        income_before = len(self.strategy.income_list)
        expense_before = len(self.strategy.expense_list)
        self.strategy.template_parser(order)
        if len(self.strategy.income_list) > income_before:
            return "income", self.strategy.income_list[-1]
        if len(self.strategy.expense_list) > expense_before:
            return "expense", self.strategy.expense_list[-1]
        raise ValueError("渲染策略未生成交易")


class Compiler(CoreCompiler):
    def __init__(self, provider, config, ir, template_strategy, analyser):
        super().__init__(
            provider,
            ir,
            _LegacyRenderer(template_strategy),
            lambda order: analyser.get_account_and_tags(order, config),
            lambda prepared: apply_post_processor(provider, prepared, config),
            default_minus_account=config.default_minus_account,
            default_plus_account=config.default_plus_account,
        )
        self.config = config
        self.analyser = analyser
        self.template_strategy = template_strategy
        self.privider = provider
        self.source_file = ""

    def compile(self):
        print(json.dumps(self.build_result(), ensure_ascii=False))

    def render_orders(self, orders=None):
        for order in orders if orders is not None else self.ir.orders:
            self.template_strategy.template_parser(order)

    def build_entries(self, source_file=""):
        self.source_file = source_file
        return super().build_entries(source_file)

