"""The canonical bill commands; legacy root commands remain compatibility aliases."""

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from fane.cli import app, get_cli_context
from fane.shared.journal.writer import JournalWriter
from fane.shared.output import ConversionFormat, command_errors, output_text
from fane.shared.results import RenderedEntry

from .jobs import sync_job
from .legacy import _convert_bill, _echo_summary, _entry_to_json, inspect_bill

bill_app = typer.Typer(help="转换、检查、预览或写入第三方账单。", no_args_is_help=True)
app.add_typer(bill_app, name="bill")
ProviderOption = Annotated[
    str, typer.Option("--provider", "-p", help="账单来源；用 fa providers list 查看")
]
SourceOption = Annotated[
    Path, typer.Option("--source", "-s", help="账单 CSV/XLSX 文件")
]
TemplateOption = Annotated[
    Path | None, typer.Option("--template", help="本次转换使用的自定义 Jinja2 模板")
]


@bill_app.command("convert")
def convert(
    ctx: typer.Context,
    provider: ProviderOption,
    source: SourceOption,
    output_format: Annotated[
        ConversionFormat, typer.Option("--format", "-f", help="输出格式")
    ] = ConversionFormat.beancount,
    output: Annotated[
        str, typer.Option("--output", "-o", help="输出文件；- 表示 stdout")
    ] = "-",
    template: TemplateOption = None,
):
    """只转换、不导入；默认输出 Beancount 文本。"""
    with command_errors("转换失败"):
        result = _convert_bill(ctx, provider, str(source), template)
        entries = sorted(result.entries, key=lambda entry: (entry.date, entry.content))
        rows = [{**asdict(entry), "date": entry.date.isoformat()} for entry in entries]
        if output_format == ConversionFormat.beancount:
            content = "\n".join(entry.content for entry in entries)
        elif output_format == ConversionFormat.json:
            content = json.dumps(rows, ensure_ascii=False, indent=2)
        elif output_format == ConversionFormat.jsonl:
            content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        else:
            content = json.dumps(result.grouped(), ensure_ascii=False)
        output_text(content, output)


@bill_app.command("inspect")
def inspect(
    ctx: typer.Context,
    provider: ProviderOption,
    source: SourceOption,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 检查摘要")] = False,
    template: TemplateOption = None,
):
    """只读检查条数、月份和待分类交易。"""
    inspect_bill(ctx, provider, str(source), as_json, template)


@bill_app.command("import")
def import_entries(
    ctx: typer.Context,
    provider: ProviderOption,
    source: SourceOption,
    journal_dir: Annotated[
        Path, typer.Option("--journal-dir", help="账本的 journal 目录")
    ],
    write: Annotated[
        bool, typer.Option("--write", help="正式写入；默认仅预览 JSONL")
    ] = False,
    dedupe_index: Annotated[
        str, typer.Option("--dedupe-index", help="覆盖指纹索引位置")
    ] = "",
    force: Annotated[
        bool, typer.Option("--force", help="绕过去重；可能写入重复交易")
    ] = False,
    require_classified: Annotated[
        bool, typer.Option("--require-classified", help="存在待分类交易时拒绝导入")
    ] = False,
    summary: Annotated[
        bool, typer.Option("--summary", help="向 stderr 打印检查摘要")
    ] = False,
    template: TemplateOption = None,
):
    """预览导入计划；加 --write 才写入账本与去重索引。"""
    with command_errors("导入失败"):
        result = _convert_bill(ctx, provider, str(source), template)
        inspection = result.summary()
        if summary:
            _echo_summary(inspection, err=True)
        if require_classified and inspection["unmatched"]:
            raise ValueError(f"拒绝导入: 仍有 {inspection['unmatched']} 条待分类交易")
        writer = JournalWriter(
            journal_dir, dedupe_index=dedupe_index or None, force=force
        )
        if write:
            typer.echo(json.dumps(writer.write(result.entries), ensure_ascii=False))
        else:
            for entry in writer.plan(result.entries):
                typer.echo(_entry_to_json(entry))


@bill_app.command("sync")
def sync(
    ctx: typer.Context,
    job: Annotated[str, typer.Argument(help="YAML 中 jobs 下的任务名称")],
    write: Annotated[
        bool, typer.Option("--write", help="正式同步；默认仅预览")
    ] = False,
    run_date: Annotated[
        str, typer.Option("--date", help="YYYY-MM-DD；默认任务时区的今天")
    ] = "",
    as_json: Annotated[bool, typer.Option("--json", help="JSON 同步报告")] = False,
    rescan: Annotated[
        bool, typer.Option("--rescan", help="忽略文件缓存，保留交易去重")
    ] = False,
    require_classified: Annotated[
        bool, typer.Option("--require-classified", help="存在待分类交易时拒绝写入")
    ] = False,
    template: TemplateOption = None,
):
    """按任务配置预览或增量同步多个来源。"""
    sync_job(
        ctx, job, run_date, not write, as_json, rescan, require_classified, template
    )


@bill_app.command("jobs")
def jobs(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 任务名称列表")] = False,
):
    """列出可传给 bill sync 的任务。"""
    with command_errors("读取任务失败"):
        names = sorted((get_cli_context(ctx).config.jobs or {}).keys())
        typer.echo(
            json.dumps(names, ensure_ascii=False)
            if as_json
            else "\n".join(names) or "未配置同步任务"
        )


@bill_app.command("ingest")
def ingest(
    journal: Annotated[Path, typer.Argument(help="目标 journal 目录")],
    input_file: Annotated[
        str, typer.Option("--input", "-i", help="JSONL 文件；- 读取 stdin")
    ] = "-",
    write: Annotated[bool, typer.Option("--write", help="正式写入；默认预览")] = False,
    dedupe_index: Annotated[str, typer.Option("--dedupe-index")] = "",
):
    """读取 convert --format jsonl 的结果，保持指纹去重和分录文本。"""
    with command_errors("导入失败"):
        text = sys.stdin.read() if input_file == "-" else Path(input_file).read_text()
        entries = []
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("JSONL 每行必须是分录对象")
            required = {
                "date",
                "month",
                "kind",
                "fingerprint",
                "content",
                "source_provider",
                "source_file",
            }
            if not required <= row.keys() or row.keys() - required - {"order_id"}:
                raise ValueError("JSONL 分录字段与 convert 输出不符")
            if any(not isinstance(row[key], str) for key in required):
                raise ValueError("JSONL 分录字段必须是字符串")
            row["date"] = date.fromisoformat(row["date"])
            if row["month"] != row["date"].strftime("%m") or row["kind"] not in {
                "expense",
                "income",
            }:
                raise ValueError("JSONL 分录的月份或类型无效")
            entry = RenderedEntry(**row)
            if not entry.fingerprint or not entry.content.strip():
                raise ValueError("JSONL 分录必须有指纹和文本")
            entries.append(entry)
        writer = JournalWriter(journal, dedupe_index=dedupe_index or None)
        if write:
            typer.echo(json.dumps(writer.write(entries), ensure_ascii=False))
        else:
            for entry in writer.plan(entries):
                typer.echo(_entry_to_json(entry))
