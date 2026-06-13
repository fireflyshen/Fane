from typing import Protocol

from ir.ir import Order
from package.config import Config
from package.parser.ali.alipay import AlipayAnalyser
from package.parser.wechat.wechat import WechatAnalyser

analyser_dict = {"alipay": AlipayAnalyser, "wechat": WechatAnalyser}


class Paser(Protocol):
    def get_account_and_tags(self, o: Order, cfg: Config) -> tuple:
        pass


def get_analyser(provider_name: str):
    analyser_factory = analyser_dict.get(provider_name)
    if analyser_factory is None:
        return None
    return analyser_factory()
