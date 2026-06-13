import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Pattern

from ir.ir import IR, Order
from package.config import Config
from package.parser.paser import Paser
from package.strategy.template.strategy import TemplateStrategy

MONTH_PATTERN: Pattern[str] = re.compile(r"^\d{4}-(\d{2})-\d{2}")
PostProcessor = Callable[[IR], IR]


def _post_process_alipay(ir: IR) -> IR:
    from provider.ali.processor import post_process

    return post_process(ir)


POST_PROCESSORS: dict[str, PostProcessor] = {"alipay": _post_process_alipay}


class Compiler:
    def __init__(
        self,
        privider: str,
        config: Config,
        ir: IR,
        template_strategy: TemplateStrategy,
        analyser: Paser,
    ):
        self.provider = privider
        self.privider = privider
        self.config = config
        self.ir = ir
        self.template_strategy = template_strategy
        self.analyser = analyser

    def compile(self):
        logging.debug("start compile")
        data_str = json.dumps(self.build_result(), ensure_ascii=False)
        print(data_str)

    def build_result(self) -> dict:
        self.apply_accounts()
        self.apply_provider_post_process()
        self.render_orders()

        expense_data = self.distribution(self.template_strategy.expense_list)
        income_data = self.distribution(self.template_strategy.income_list)

        return {
            "expense": {k: sorted(v) for k, v in sorted(expense_data.items())},
            "income": {k: sorted(v) for k, v in sorted(income_data.items())},
        }

    def apply_accounts(self) -> None:
        orders: list[Order] = []
        for o in self.ir.orders:
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

        self.ir.orders = orders

    def apply_provider_post_process(self) -> None:
        post_processor = POST_PROCESSORS.get(self.provider)
        if post_processor is not None:
            self.ir = post_processor(self.ir)

    def render_orders(self) -> None:
        for io in self.ir.orders:
            self.template_strategy.template_parser(io)

    def distribution(self, bean_bill_list: list):
        monthly_data = defaultdict(list)

        for item in bean_bill_list:
            match_obj = MONTH_PATTERN.match(item)
            if match_obj:
                month = match_obj.group(1)
                monthly_data[month].append(item)
        return dict(monthly_data)
