"""账单流水线：读取、匹配账户、处理还款、渲染分录。"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fane.shared.config import Config
from fane.shared.errors import ProviderError
from fane.shared.render.normal import NormalStrategy
from fane.shared.results import RenderedEntry, fingerprint_order


def provider_names() -> tuple[str, ...]:
    root = Path(__file__).parent / "providers"
    return tuple(
        name for name in ("alipay", "wechat") if (root / name / "reader.py").is_file()
    )


@dataclass(frozen=True)
class ConversionResult:
    provider: str
    source: str
    entries: list[RenderedEntry]
    unmatched: int

    def summary(self) -> dict[str, object]:
        months: dict[str, int] = {}
        for entry in self.entries:
            key = f"{entry.date.year}-{entry.month}"
            months[key] = months.get(key, 0) + 1
        return {
            "provider": self.provider,
            "source": self.source,
            "total": len(self.entries),
            "expense": sum(entry.kind == "expense" for entry in self.entries),
            "income": sum(entry.kind == "income" for entry in self.entries),
            "unmatched": self.unmatched,
            "months": dict(sorted(months.items())),
        }


class Converter:
    def __init__(self, config: Config, template_file: Path | None = None):
        self.config = config
        self.renderer = NormalStrategy(
            template_file
            or (Path(config.template_file) if config.template_file else None)
        )

    def convert(self, provider: str, source: str) -> ConversionResult:
        if provider not in provider_names():
            raise ProviderError(
                f"不支持的 provider: {provider}，可选值有: {', '.join(provider_names())}"
            )
        if provider == "alipay":
            from .providers.alipay.reader import AliPay
            from .rules.alipay import AlipayAnalyser

            ir = AliPay().translate(source)
            analyser = AlipayAnalyser()
        else:
            from .providers.wechat.reader import Wechat
            from .rules.wechat import WechatAnalyser

            ir = Wechat().translate(source)
            analyser = WechatAnalyser()

        orders = []
        for order in ir.orders:
            ignore, minus, plus, extra, tags = analyser.get_account_and_tags(
                order, self.config
            )
            if ignore:
                continue
            order.minus_account, order.plus_account = minus or "", plus or ""
            order.extra_account, order.tags = extra, tags
            orders.append(order)
        ir.orders = orders

        if provider == "alipay":
            from .repayments import post_process

            ir = post_process(ir, self.config)

        entries = []
        unmatched = 0
        for order in ir.orders:
            kind, content = self.renderer.render_order(order)
            day = (
                order.pay_time.date()
                if order.pay_time
                else date.fromisoformat(content[:10])
            )
            entries.append(
                RenderedEntry(
                    date=day,
                    month=f"{day.month:02d}",
                    kind=kind,
                    fingerprint=fingerprint_order(provider, order),
                    content=content,
                    source_provider=provider,
                    source_file=source,
                    order_id=order.order_id or order.meta_data.get("order_id") or None,
                )
            )
            if (
                self.config.default_minus_account
                and order.minus_account == self.config.default_minus_account
            ) or (
                self.config.default_plus_account
                and order.plus_account == self.config.default_plus_account
            ):
                unmatched += 1
        return ConversionResult(provider, source, entries, unmatched)
