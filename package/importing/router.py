from __future__ import annotations

from pathlib import Path

from package.compiler.results import RenderedEntry
from package.config import RoutingConfig
from package.errors import SyncError


class JournalRouter:
    def __init__(self, journal_dir: str | Path, routing: RoutingConfig):
        self.journal_dir = Path(journal_dir).expanduser().resolve()
        self.routing = routing

    def target_file(self, entry: RenderedEntry) -> Path:
        template = (
            self.routing.income if entry.kind == "income" else self.routing.expense
        )
        try:
            rendered = template.format(
                year=f"{entry.date.year:04d}",
                month=f"{entry.date.month:02d}",
                kind=entry.kind,
                provider=entry.source_provider,
            )
        except (KeyError, ValueError) as error:
            raise SyncError(f"无效的 routing 模板 {template!r}: {error}") from error

        relative = Path(rendered)
        if relative.is_absolute() or ".." in relative.parts:
            raise SyncError(f"routing 只能生成 journal-dir 内的相对路径: {rendered}")
        target = (self.journal_dir / relative).resolve()
        try:
            target.relative_to(self.journal_dir)
        except ValueError as error:
            raise SyncError(f"routing 路径越过 journal-dir: {rendered}") from error
        return target
