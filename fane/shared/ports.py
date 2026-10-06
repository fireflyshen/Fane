"""Contracts at the conversion boundary; no concrete adapters belong here."""

from collections.abc import Callable
from typing import Protocol

from .models import IR, Order
from .rules import AccountResolutionTuple


class Provider(Protocol):
    def translate(self, filename: str) -> IR: ...


class OrderRenderer(Protocol):
    def render_order(self, order: Order) -> tuple[str, str]: ...


ProviderFactory = Callable[[], Provider]
AccountResolver = Callable[[Order], AccountResolutionTuple]
PostProcessor = Callable[[IR], IR]
