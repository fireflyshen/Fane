from typing import Protocol

from ir.ir import Order
from package.config import Config
from package.parser.ali.alipay import AlipayAnalyser
from package.parser.wechat.wechat import WechatAnalyser


class Paser(Protocol):
    def get_account_and_tags(self, o: Order, cfg: Config) -> tuple:
        pass


def get_analyser(provider_name: str):
    if provider_name == "alipay":
        return AlipayAnalyser()
    if provider_name == "wechat":
        return WechatAnalyser()
    return None
