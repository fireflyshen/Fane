import json
import traceback
from dataclasses import asdict
from pathlib import Path

import typer
from typing_extensions import Annotated

from fane.bill.build import build_converter
from fane.cli import app, get_cli_context
from fane.shared.conversion import ConversionResult
from fane.shared.errors import FaneError, ProviderError
from fane.shared.journal.writer import JournalWriter


def _convert_bill(
    ctx: typer.Context, provider: str, source: str, template: Path | None = None
) -> ConversionResult:
    context = get_cli_context(ctx)
    converter = (
        build_converter(context.config, template_file=template)
        if template
        else context.converter
    )
    if provider not in converter.providers:
        supported = ", ".join(converter.providers)
        raise ProviderError(f"不支持的 provider: {provider}，可选值有: {supported}")
    if not source:
        typer.echo("请通过 --source/-s 指定账单文件", err=True)
        raise typer.Exit(code=1)
    if not Path(source).is_file():
        typer.echo(f"账单文件不存在: {source}", err=True)
        raise typer.Exit(code=1)
    return converter.convert(provider, source)


def _entry_to_json(entry) -> str:
    data = asdict(entry)
    data["date"] = entry.date.isoformat()
    return json.dumps(data, ensure_ascii=False)


def _echo_summary(summary: dict[str, object], *, err: bool = False) -> None:
    typer.echo(
        "检查摘要: "
        f"共 {summary['total']} 条，支出 {summary['expense']}，"
        f"收入 {summary['income']}，待分类 {summary['unmatched']}",
        err=err,
    )


@app.command(hidden=True)
def trans(
    ctx: typer.Context,
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Bills provider")
    ] = "alipay",
    source: Annotated[str, typer.Option("--source", "-s", help="source file")] = "",
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="output format: json, beancount, jsonl",
        ),
    ] = "json",
    template: Annotated[
        Path | None, typer.Option("--template", help="覆盖内置或配置中的模板")
    ] = None,
) -> None:
    try:
        converted = _convert_bill(ctx, provider, source, template)
        if output_format == "json":
            print(json.dumps(converted.grouped(), ensure_ascii=False))
            return
        entries = converted.entries
        if output_format == "beancount":
            for entry in sorted(entries, key=lambda item: (item.date, item.content)):
                print(entry.content)
            return
        if output_format == "jsonl":
            for entry in sorted(entries, key=lambda item: (item.date, item.content)):
                print(_entry_to_json(entry))
            return
        typer.echo(
            f"不支持的输出格式: {output_format}，可选值: json, beancount, jsonl",
            err=True,
        )
        raise typer.Exit(code=1)
    except FaneError as e:
        typer.echo(f"编译出错: {e}", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command("inspect", hidden=True)
def inspect_bill(
    ctx: typer.Context,
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Bills provider")
    ] = "alipay",
    source: Annotated[str, typer.Option("--source", "-s", help="source file")] = "",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="以 JSON 输出检查摘要"),
    ] = False,
    template: Annotated[
        Path | None, typer.Option("--template", help="覆盖内置或配置中的模板")
    ] = None,
) -> None:
    """只读检查账单条数、月份和待分类数量，不写入账本。"""
    try:
        summary = _convert_bill(ctx, provider, source, template).summary()
        if as_json:
            print(json.dumps(summary, ensure_ascii=False))
            return
        typer.echo(f"来源: {summary['provider']}")
        typer.echo(f"账单: {summary['source']}")
        _echo_summary(summary)
        months = summary["months"]
        if isinstance(months, dict):
            typer.echo(
                "月份: "
                + ", ".join(f"{month}={count}" for month, count in months.items())
            )
    except FaneError as error:
        typer.echo(f"检查出错: {error}", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(f"检查出错: {error}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command("import", hidden=True)
def import_bill(
    ctx: typer.Context,
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Bills provider")
    ] = "alipay",
    source: Annotated[str, typer.Option("--source", "-s", help="source file")] = "",
    journal_dir: Annotated[
        Path,
        typer.Option(
            "--journal-dir",
            "-o",
            help="journal root directory; entries are written under YEAR/",
        ),
    ] = Path.home() / ".flow" / "account" / "journal",
    dedupe_index: Annotated[
        str,
        typer.Option(
            "--dedupe-index",
            help="jsonl fingerprint index path; defaults in the external Fane state directory",
        ),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="print planned entries without writing files"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="write entries even if fingerprints already exist"
        ),
    ] = False,
    require_classified: Annotated[
        bool,
        typer.Option(
            "--require-classified",
            help="存在使用默认账户的待分类交易时拒绝写入",
        ),
    ] = False,
    summary: Annotated[
        bool,
        typer.Option("--summary", help="在标准错误中输出导入前摘要"),
    ] = False,
    template: Annotated[
        Path | None, typer.Option("--template", help="覆盖内置或配置中的模板")
    ] = None,
) -> None:
    try:
        converted = _convert_bill(ctx, provider, source, template)
        entries = converted.entries
        inspection = converted.summary()
        if summary:
            _echo_summary(inspection, err=True)
        if require_classified and inspection["unmatched"]:
            typer.echo(
                f"拒绝导入: 仍有 {inspection['unmatched']} 条交易使用默认账户",
                err=True,
            )
            raise typer.Exit(code=1)
        if dry_run:
            for entry in sorted(entries, key=lambda item: (item.date, item.content)):
                print(_entry_to_json(entry))
            return
        writer = JournalWriter(
            journal_dir,
            dedupe_index=dedupe_index or None,
            force=force,
        )
        result = writer.write(entries)
        print(json.dumps(result, ensure_ascii=False))
    except FaneError as e:
        typer.echo(f"编译出错: {e}", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)
