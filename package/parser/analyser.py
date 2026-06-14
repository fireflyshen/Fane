from typing import Protocol

from ir.ir import Order
from package.config import Config
from package.parser.ali.alipay import AlipayAnalyser
from package.parser.rule_resolver import AccountResolutionTuple
from package.parser.wechat.wechat import WechatAnalyser


class Analyser(Protocol):
    def get_account_and_tags(
        self, order: Order, config: Config
    ) -> AccountResolutionTuple:
        ...


ANALYSERS = {
    "alipay": AlipayAnalyser,
    "wechat": WechatAnalyser,
}


def create_analyser(provider_name: str) -> Analyser | None:
    analyser_factory = ANALYSERS.get(provider_name)
    if analyser_factory is None:
        return None
    return analyser_factory()
