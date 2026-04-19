from provider.ali.alipay import AliPay
from provider.wechat.wechat import Wechat


provider_dict = {"alipay": AliPay(), "wechat": Wechat()}


def get_provider(provider_name: str):
    return provider_dict.get(provider_name, None)
