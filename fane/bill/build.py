"""Composition root: the only registration point for concrete conversion adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from fane.modules import provider_names
from fane.shared.config import Config, SyncJob
from fane.shared.conversion import ConversionService, ProviderBinding
from fane.shared.models import IR, Order
from fane.shared.ports import ProviderFactory
from fane.shared.render.normal import NormalStrategy
from fane.shared.rules import AccountResolutionTuple

if TYPE_CHECKING:
    from fane.bill.sync import SyncService


class Analyser(Protocol):
    def get_account_and_tags(
        self, order: Order, config: Config
    ) -> AccountResolutionTuple: ...


@dataclass(frozen=True)
class ProviderSpec:
    reader: ProviderFactory
    analyser: Callable[[], Analyser]
    post_processor: Callable[[IR, Config], IR] | None = None


def _factory(module, name):
    return lambda: getattr(import_module(module), name)()


def _repayments(ir, config):
    return import_module("fane.bill.repayments").post_process(ir, config)


PROVIDER_SPECS = {
    name: ProviderSpec(
        _factory(
            f"fane.bill.providers.{name}.reader",
            "AliPay" if name == "alipay" else "Wechat",
        ),
        _factory(
            f"fane.bill.rules.{name}",
            "AlipayAnalyser" if name == "alipay" else "WechatAnalyser",
        ),
        _repayments if name == "alipay" else None,
    )
    for name in provider_names()
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
    from fane.bill.sync import SyncService

    return SyncService(
        config,
        job_name,
        job,
        converter=build_converter(config, template_file=template_file),
    )
