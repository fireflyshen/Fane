"""Installed CLI for exporting and applying externally supplied classification decisions."""

import shlex
import sys
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

from fane.application import fixme

from .common import command_errors, output_json, output_text
from .ledger import LedgerOption, context
from .root import app, get_cli_context

classify_app = typer.Typer(
    help="导出待分类交易、查看决策格式、预览或应用外部分类结果。", no_args_is_help=True
)
app.add_typer(classify_app, name="classify")
RootOption = Annotated[
    Path | None,
    typer.Option(
        "--root",
        envvar="BILLS_ROOT",
        help="扫描 journal/ 与 accounts/data/ 的账本根目录",
    ),
]


@classify_app.command("schema")
def schema(
    output: Annotated[
        str, typer.Option("--output", "-o", help="输出文件；- 表示 stdout")
    ] = "-",
):
    """输出外部 AI/人工决策所需的 JSON Schema；不调用模型。"""
    with command_errors("读取决策格式失败"):
        output_text(
            files("fane.application")
            .joinpath("ai-fixme-decision.schema.json")
            .read_text(encoding="utf-8"),
            output,
        )


@classify_app.command("extract")
def extract(
    ctx: typer.Context,
    ledger: LedgerOption = None,
    root: RootOption = None,
    output: Annotated[
        str, typer.Option("--output", "-o", help="JSON 文件；- 表示 stdout")
    ] = "-",
):
    """只读导出占位账户分录、账户目录和来源字段。"""
    with command_errors("分类导出失败"):
        location = root.expanduser().resolve() if root else context(ledger, ctx).root
        output_json(fixme.extraction_payload(location), output)


@classify_app.command("apply")
def apply(
    ctx: typer.Context,
    ledger: LedgerOption = None,
    root: RootOption = None,
    input_file: Annotated[
        str, typer.Option("--input", "-i", help="决策 JSON 文件；默认 - 从 stdin 读取")
    ] = "-",
    input_base64: Annotated[
        str | None,
        typer.Option(
            "--input-base64", help="UTF-8 决策 JSON 的 Base64，与文件输入互斥"
        ),
    ] = None,
    write: Annotated[
        bool, typer.Option("--write", help="正式修改账户并追加规则；默认仅预览")
    ] = False,
    min_confidence: Annotated[
        float, typer.Option("--min-confidence", min=0, max=1, help="最低应用置信度")
    ] = 0.92,
    allow_partial: Annotated[
        bool, typer.Option("--allow-partial", help="允许保留缺失/暂缓的决策")
    ] = False,
    validators: Annotated[
        list[str] | None,
        typer.Option(
            "--validator", help="额外指定的校验命令，可重复；替代默认账本校验"
        ),
    ] = None,
    skip_config_check: Annotated[
        bool, typer.Option("--skip-config-check", help="跳过落盘后的配置诊断")
    ] = False,
):
    """检查决策；加 --write 后修改账本/配置，校验失败回滚。"""
    with command_errors("分类应用失败", code=2, json_error=True):
        if input_base64 is not None and input_file != "-":
            raise ValueError("--input 文件与 --input-base64 不能同时指定")
        ctx_ledger = context(ledger, ctx)
        location = root.expanduser().resolve() if root else ctx_ledger.root
        config_path = get_cli_context(ctx).config_path.resolve()
        payload = fixme._load_decisions(
            None if input_base64 is not None else input_file, input_base64
        )
        decisions = fixme.validate_decisions(
            location,
            payload,
            min_confidence=min_confidence,
            allow_partial=allow_partial,
        )
        checks = (
            list(validators)
            if validators
            else [
                shlex.join(
                    [
                        sys.executable,
                        "-m",
                        "fane",
                        "--config",
                        str(config_path),
                        "ledger",
                        "validate",
                        "--ledger",
                        str(ctx_ledger.ledger),
                    ]
                )
            ]
        )
        if not skip_config_check:
            checks.insert(
                0,
                shlex.join(
                    [
                        sys.executable,
                        "-m",
                        "fane",
                        "--config",
                        str(config_path),
                        "config",
                        "check",
                    ]
                ),
            )
        result = fixme._apply_changes(
            location,
            decisions,
            config_path=config_path,
            dry_run=not write,
            fane_command=None,
            validators=checks,
        )
        output_json(result)
