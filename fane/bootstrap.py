"""Composition root: the only registration point for concrete conversion adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from fane.application.classification.alipay import AlipayAnalyser
from fane.application.classification.wechat import WechatAnalyser
from fane.application.repayments import post_process
from fane.config import Config, SyncJob
from fane.core.conversion import ConversionService, ProviderBinding
from fane.core.models import IR, Order
from fane.core.ports import ProviderFactory
from fane.core.rules import AccountResolutionTuple
from fane.infrastructure.rendering.normal import NormalStrategy
from fane.providers.alipay.reader import AliPay
from fane.providers.wechat.reader import Wechat

if TYPE_CHECKING:
    from fane.application.sync import SyncService


class Analyser(Protocol):
    def get_account_and_tags(
        self, order: Order, config: Config
    ) -> AccountResolutionTuple: ...


@dataclass(frozen=True)
class ProviderSpec:
    reader: ProviderFactory
    analyser: Callable[[], Analyser]
    post_processor: Callable[[IR, Config], IR] | None = None


PROVIDER_SPECS = {
    "alipay": ProviderSpec(AliPay, AlipayAnalyser, post_process),
    "wechat": ProviderSpec(Wechat, WechatAnalyser),
}


def supported_provider_names() -> tuple[str, ...]:
    return tuple(PROVIDER_SPECS)


def _bind(
    spec: ProviderSpec, config: Config, template_file: Path | None
) -> ProviderBinding:
    analyser = spec.analyser()
    return ProviderBinding(
        reader=spec.reader,
        resolver=lambda order: analyser.get_account_and_tags(order, config),
        post_processor=lambda ir: (
            spec.post_processor(ir, config) if spec.post_processor else ir
        ),
        renderer=lambda: NormalStrategy(template_file),
    )


def build_converter(
    config: Config,
    *,
    specs: Mapping[str, ProviderSpec] | None = None,
    template_file: Path | None = None,
) -> ConversionService:
    template_file = template_file or (
        Path(config.template_file) if config.template_file else None
    )
    definitions = PROVIDER_SPECS if specs is None else specs
    return ConversionService(
        {
            name: _bind(spec, config, template_file)
            for name, spec in definitions.items()
        },
        default_minus_account=config.default_minus_account,
        default_plus_account=config.default_plus_account,
    )


def build_sync_service(
    config: Config, job_name: str, job: SyncJob, *, template_file: Path | None = None
) -> SyncService:
    from fane.application.sync import SyncService

    return SyncService(
        config,
        job_name,
        job,
        converter=build_converter(config, template_file=template_file),
    )
