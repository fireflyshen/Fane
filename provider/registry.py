from collections.abc import Callable
from typing import Protocol, TypeAlias

from ir.ir import IR
from provider.ali.alipay import AliPay
from provider.wechat.wechat import Wechat


class Provider(Protocol):
    def translate(self, filename: str) -> IR:
        ...


ProviderFactory: TypeAlias = Callable[[], Provider]

PROVIDERS: dict[str, ProviderFactory] = {
    "alipay": AliPay,
    "wechat": Wechat,
}


def create_provider(provider_name: str) -> Provider | None:
    provider_factory = PROVIDERS.get(provider_name)
    if provider_factory is None:
        return None
    return provider_factory()


def supported_provider_names() -> tuple[str, ...]:
    return tuple(PROVIDERS)
