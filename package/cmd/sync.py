from __future__ import annotations

from datetime import date
import json

import typer
from typing_extensions import Annotated

from package.config import get_config_model
from package.errors import FaneError, SyncError
from package.importing import SyncReport, SyncService
from .root import app


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SyncError("--date 必须使用 YYYY-MM-DD 格式") from error


def _print_report(report: SyncReport) -> None:
    typer.echo(f"同步任务: {report.job} ({report.date})")
    for source in report.sources:
        location = f" -> {source.path}" if source.path else ""
        typer.echo(
            f"- {source.source_id}: {source.status}{location}"
            f"，交易 {source.entries}，待分类 {source.unmatched}"
        )
    typer.echo(
        f"结果: {report.status}，读取 {report.total}，"
        f"写入 {report.written}，去重 {report.skipped}"
    )
    for target, count in report.targets.items():
        typer.echo(f"  {target}: +{count}")


@app.command("sync")
def sync_job(
    job_name: Annotated[str, typer.Argument(help="config.yaml 中 jobs 下的任务名")],
    run_date: Annotated[
        str,
        typer.Option("--date", help="处理日期，格式 YYYY-MM-DD；默认使用任务时区的今天"),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="完整解析并展示计划，但不写账本或状态"),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="以 JSON 输出同步报告"),
    ] = False,
    rescan: Annotated[
        bool,
        typer.Option("--rescan", help="忽略文件级缓存重新解析，仍保留交易去重"),
    ] = False,
    require_classified: Annotated[
        bool,
        typer.Option("--require-classified", help="存在待分类交易时拒绝写入"),
    ] = False,
) -> None:
    """按配置任务增量导入一个或多个账单来源。"""
    try:
        config = get_config_model()
        jobs = config.jobs or {}
        job = jobs.get(job_name)
        if job is None:
            available = ", ".join(sorted(jobs)) or "(未配置 jobs)"
            raise SyncError(f"未找到同步任务 {job_name!r}；可选值: {available}")
        report = SyncService(config, job_name, job).run(
            run_date=_parse_date(run_date),
            dry_run=dry_run,
            rescan=rescan,
            require_classified=True if require_classified else None,
        )
        if as_json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
        else:
            _print_report(report)
    except FaneError as error:
        typer.echo(f"同步失败: {error}", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(f"同步失败: {error}", err=True)
        raise typer.Exit(code=1)
