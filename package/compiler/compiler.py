import logging

from package.config import Config
from ir.ir import IR, Order
from package.strategy.template.strategy import TemplateStrategy
from package.parser.paser import Paser
import re
import json
from collections import defaultdict


class Compiler:
    def __init__(
        self,
        privider: str,
        config: Config,
        ir: IR,
        template_strategy: TemplateStrategy,
        analyser: Paser,
    ):
        self.privider = privider
        self.config = config
        self.ir = ir
        self.template_strategy = template_strategy
        self.analyser = analyser

    def compile(self):
        logging.debug("start compile")
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

        if self.privider == "alipay":
            from provider.ali.processor import post_process

            self.ir = post_process(self.ir)

        for io in self.ir.orders:
            self.template_strategy.template_parser(io)
        expense_data = self.distribution(self.template_strategy.expense_list)
        income_data = self.distribution(self.template_strategy.income_list)

        result = {
            "expense": {k: sorted(v) for k, v in sorted(expense_data.items())},
            "income": {k: sorted(v) for k, v in sorted(income_data.items())},
        }

        data_str = json.dumps(result, ensure_ascii=False)
        print(data_str)

    def distribution(self, bean_bill_list: list):
        r = r"^\d{4}-(\d{2})-\d{2}"
        monthly_data = defaultdict(list)

        for item in bean_bill_list:
            match_obj = re.match(r, item)
            if match_obj:
                month = match_obj.group(1)
                monthly_data[month].append(item)
        return dict(monthly_data)
