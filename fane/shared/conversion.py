"""The shared application boundary for CLI conversion and scheduled imports."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .compiler import CompiledResult, Compiler, group_entries
from .errors import ProviderError
from .ports import AccountResolver, OrderRenderer, PostProcessor, ProviderFactory
from .results import RenderedEntry


@dataclass(frozen=True)
class ProviderBinding:
    reader: ProviderFactory
    resolver: AccountResolver
    post_processor: PostProcessor
    renderer: Callable[[], OrderRenderer]


@dataclass(frozen=True)
class ConversionResult:
    provider: str
    source: str
    entries: list[RenderedEntry]
    unmatched: int

    def grouped(self) -> CompiledResult:
        return group_entries(self.entries)

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


class ConversionService:
    def __init__(
        self,
        bindings: Mapping[str, ProviderBinding],
        *,
        default_minus_account: str | None = None,
        default_plus_account: str | None = None,
    ):
        self._bindings = dict(bindings)
        self.default_minus_account = default_minus_account
        self.default_plus_account = default_plus_account

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(self._bindings)

    def create_compiler(self, provider: str, source: str) -> Compiler:
        binding = self._bindings.get(provider)
        if binding is None:
            supported = ", ".join(self.providers)
            raise ProviderError(f"不支持的 provider: {provider}，可选值有: {supported}")
        return Compiler(
            provider,
            binding.reader().translate(source),
            binding.renderer(),
            binding.resolver,
            binding.post_processor,
            default_minus_account=self.default_minus_account,
            default_plus_account=self.default_plus_account,
        )

    def convert(self, provider: str, source: str) -> ConversionResult:
        compiler = self.create_compiler(provider, source)
        return ConversionResult(
            provider, source, compiler.build_entries(source), compiler.unmatched_count()
        )
