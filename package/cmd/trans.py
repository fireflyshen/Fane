import json
import traceback
from dataclasses import asdict
from pathlib import Path

import typer
from typing_extensions import Annotated

from package.compiler.compiler import Compiler
from package.compiler.writer import JournalWriter
from package.config import get_config_model
from package.errors import FaneError
from package.parser.analyser import create_analyser
from package.strategy.template.normal import NormalStrategy
from provider.registry import create_provider, supported_provider_names
from .root import app


def _create_compiler(provider: str, source: str) -> Compiler:
    p = create_provider(provider)
    if p is None:
        supported = ", ".join(supported_provider_names())
        typer.echo(f"不支持的 provider: {provider}，可选属有: {supported}")
        raise typer.Exit(code=1)
    if not source:
        typer.echo("请通过 --source/-s 指定账单文件", err=True)
        raise typer.Exit(code=1)
    if not Path(source).is_file():
        typer.echo(f"账单文件不存在: {source}", err=True)
        raise typer.Exit(code=1)
    analyser = create_analyser(provider)
    if analyser is None:
        typer.echo(f"不支持的 analyser: {provider}", err=True)
        raise typer.Exit(code=1)
    ir = p.translate(source)
    config = get_config_model()
    return Compiler(provider, config, ir, NormalStrategy(), analyser)


def _entry_to_json(entry) -> str:
    data = asdict(entry)
    data["date"] = entry.date.isoformat()
    return json.dumps(data, ensure_ascii=False)


@app.command()
def trans(
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
) -> None:
    try:
        compiler = _create_compiler(provider, source)
        if output_format == "json":
            compiler.compile()
            return
        entries = compiler.build_entries(source)
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
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command("import")
def import_bill(
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
            help="jsonl fingerprint index path; defaults beside journal root",
        ),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="print planned entries without writing files"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="write entries even if fingerprints already exist"),
    ] = False,
) -> None:
    try:
        compiler = _create_compiler(provider, source)
        entries = compiler.build_entries(source)
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
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)
