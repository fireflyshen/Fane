from collections.abc import Callable
from typing import Any, TypeAlias

from provider.ali.alipay import AliPay
from provider.base import TabularProvider
from provider.wechat.wechat import Wechat

ProviderFactory: TypeAlias = Callable[[], TabularProvider[Any]]

provider_dict: dict[str, ProviderFactory] = {"alipay": AliPay, "wechat": Wechat}


def get_provider(provider_name: str):
    provider_factory = provider_dict.get(provider_name)
    if provider_factory is None:
        return None
    return provider_factory()
