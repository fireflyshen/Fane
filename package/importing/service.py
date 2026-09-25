from __future__ import annotations

import glob as glob_module
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from package.compiler.compiler import Compiler
from package.compiler.results import RenderedEntry
from package.compiler.writer import JournalWriter
from package.config import Config, SourceConfig, SyncJob
from package.errors import SyncError
from package.importing.router import JournalRouter
from package.importing.state import SyncLock, SyncState, sha256_file
from package.parser.analyser import create_analyser
from package.strategy.template.normal import NormalStrategy
from provider.registry import create_provider, supported_provider_names


@dataclass
class SourceReport:
    source_id: str
    provider: str
    path: str | None
    status: str
    sha256: str | None = None
    entries: int = 0
    unmatched: int = 0


@dataclass
class SyncReport:
    job: str
    date: str
    status: str = "success"
    sources: list[SourceReport] = field(default_factory=list)
    total: int = 0
    written: int = 0
    skipped: int = 0
    unmatched: int = 0
    targets: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SyncService:
    def __init__(self, config: Config, job_name: str, job: SyncJob):
        self.config = config
        self.job_name = job_name
        self.job = job
        self.journal_dir = Path(job.journal_dir).expanduser()
        state_root = self.journal_dir.parent / ".fane"
        self.state_file = (
            Path(job.state_file).expanduser()
            if job.state_file
            else (state_root / "sync-state.json")
        )
        self.lock_file = (
            Path(job.lock_file).expanduser()
            if job.lock_file
            else (state_root / "sync.lock")
        )
        self.dedupe_index = (
            Path(job.dedupe_index).expanduser()
            if job.dedupe_index
            else state_root / "imported.jsonl"
        )
        self.router = JournalRouter(self.journal_dir, job.routing)

    def run(
        self,
        *,
        run_date: date | None = None,
        dry_run: bool = False,
        rescan: bool = False,
        require_classified: bool | None = None,
    ) -> SyncReport:
        effective_date = run_date or self._today()
        report = SyncReport(job=self.job_name, date=effective_date.isoformat())
        with SyncLock(self.lock_file):
            state = SyncState(self.state_file)
            entries, changed = self._collect(
                state, effective_date, report, rescan=rescan
            )
            report.total = len(entries)
            report.unmatched = sum(item.unmatched for item in report.sources)
            strict = (
                self.job.require_classified
                if require_classified is None
                else require_classified
            )
            if strict and report.unmatched:
                raise SyncError(f"拒绝同步: 仍有 {report.unmatched} 条交易使用默认账户")

            writer = JournalWriter(
                self.journal_dir,
                dedupe_index=self.dedupe_index,
                target_resolver=self.router.target_file,
            )
            planned = self._planned_entries(entries, writer)
            report.skipped = len(entries) - len(planned)
            report.targets = dict(
                sorted(
                    Counter(str(writer.target_file(item)) for item in planned).items()
                )
            )
            if dry_run:
                report.status = "dry-run"
                report.written = len(planned)
                return report
            if not changed:
                report.status = "noop"
                return report

            snapshots = self._snapshot(
                {writer.target_file(item) for item in planned}
                | {self.dedupe_index, self.state_file}
            )
            try:
                result = writer.write(entries)
                report.written = result["written"]
                report.skipped = result["skipped"]
                self._run_validators()
                completed_at = datetime.now().astimezone().isoformat(timespec="seconds")
                for key, path, digest in changed:
                    stat = path.stat()
                    state.update_source(
                        key,
                        {
                            "path": str(path),
                            "sha256": digest,
                            "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                            "processed_at": completed_at,
                        },
                    )
                state.save()
            except Exception:
                self._restore(snapshots)
                raise
            return report

    def _today(self) -> date:
        try:
            timezone = ZoneInfo(self.job.timezone)
        except ZoneInfoNotFoundError as error:
            raise SyncError(f"未知时区: {self.job.timezone}") from error
        return datetime.now(timezone).date()

    def _collect(
        self,
        state: SyncState,
        run_date: date,
        report: SyncReport,
        *,
        rescan: bool,
    ) -> tuple[list[RenderedEntry], list[tuple[str, Path, str]]]:
        entries: list[RenderedEntry] = []
        changed: list[tuple[str, Path, str]] = []
        for source in self.job.sources:
            paths = self._discover(source, run_date)
            if not paths:
                policy = source.on_missing or self.job.on_missing
                report.sources.append(
                    SourceReport(source.id, source.provider, None, "missing")
                )
                if policy == "error":
                    raise SyncError(f"来源 {source.id} 未找到匹配账单")
                continue
            for path in paths:
                digest = sha256_file(path)
                key = f"{self.job_name}:{source.id}:{source.provider}:{path.resolve()}"
                if (
                    self.job.change_detection == "sha256"
                    and not rescan
                    and state.source_digest(key) == digest
                ):
                    report.sources.append(
                        SourceReport(
                            source.id, source.provider, str(path), "unchanged", digest
                        )
                    )
                    continue
                source_entries, unmatched = self._compile(source, path)
                if sha256_file(path) != digest:
                    raise SyncError(
                        f"来源 {source.id} 在解析过程中发生变化，请等待文件写入完成后重试"
                    )
                entries.extend(source_entries)
                changed.append((key, path, digest))
                report.sources.append(
                    SourceReport(
                        source.id,
                        source.provider,
                        str(path),
                        "changed",
                        digest,
                        len(source_entries),
                        unmatched,
                    )
                )
        return entries, changed

    def _discover(self, source: SourceConfig, run_date: date) -> list[Path]:
        variables = {
            "date": run_date.isoformat(),
            "year": f"{run_date.year:04d}",
            "month": f"{run_date.month:02d}",
            "day": f"{run_date.day:02d}",
        }
        template = source.path or source.glob or ""
        try:
            rendered = template.format(**variables)
        except (KeyError, ValueError) as error:
            raise SyncError(f"来源 {source.id} 的路径模板无效: {error}") from error
        if source.path is not None:
            path = Path(rendered).expanduser()
            return [path] if path.is_file() else []
        return [
            Path(value)
            for value in sorted(glob_module.glob(str(Path(rendered).expanduser())))
            if Path(value).is_file()
        ]

    def _compile(
        self, source: SourceConfig, path: Path
    ) -> tuple[list[RenderedEntry], int]:
        provider = create_provider(source.provider)
        analyser = create_analyser(source.provider)
        if provider is None or analyser is None:
            supported = ", ".join(supported_provider_names())
            raise SyncError(
                f"来源 {source.id} 使用不支持的 provider {source.provider!r}; "
                f"可选值: {supported}"
            )
        compiler = Compiler(
            source.provider,
            self.config,
            provider.translate(str(path)),
            NormalStrategy(),
            analyser,
        )
        prepared = compiler.prepare_ir()
        built = compiler.build_entries(str(path))
        default_minus = self.config.default_minus_account
        default_plus = self.config.default_plus_account
        unmatched = sum(
            1
            for order in prepared.orders or []
            if (default_minus and order.minus_account == default_minus)
            or (default_plus and order.plus_account == default_plus)
        )
        return built, unmatched

    @staticmethod
    def _planned_entries(
        entries: list[RenderedEntry], writer: JournalWriter
    ) -> list[RenderedEntry]:
        seen = set(writer.seen_fingerprints)
        planned: list[RenderedEntry] = []
        for entry in sorted(entries, key=lambda item: (item.date, item.content)):
            if entry.fingerprint in seen:
                continue
            seen.add(entry.fingerprint)
            planned.append(entry)
        return planned

    @staticmethod
    def _snapshot(paths: set[Path]) -> dict[Path, bytes | None]:
        return {path: path.read_bytes() if path.is_file() else None for path in paths}

    @staticmethod
    def _restore(snapshots: dict[Path, bytes | None]) -> None:
        for path, content in snapshots.items():
            if content is None:
                if path.exists():
                    path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def _run_validators(self) -> None:
        for validator in self.job.validators:
            try:
                result = subprocess.run(
                    validator.command,
                    cwd=Path(validator.cwd).expanduser() if validator.cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=validator.timeout_seconds,
                )
            except subprocess.TimeoutExpired as error:
                raise SyncError(
                    f"校验命令超时 ({validator.timeout_seconds}s) "
                    f"{' '.join(validator.command)}"
                ) from error
            except OSError as error:
                raise SyncError(
                    f"无法执行校验命令 {' '.join(validator.command)}: {error}"
                ) from error
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                suffix = f": {detail}" if detail else ""
                raise SyncError(
                    f"校验命令失败 ({result.returncode}) "
                    f"{' '.join(validator.command)}{suffix}"
                )
