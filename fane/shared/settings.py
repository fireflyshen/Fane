from pathlib import Path
from typing import Annotated

import typer

from fane.shared.config.diagnostics import diagnose_config
from fane.shared.context import get_cli_context
from fane.shared.output import command_errors, output_json

DEFAULT_CONFIG = """# Fane 最小配置；未匹配交易会进入 FIXME 账户，便于后续补规则。
title: Fane
default-minus-account: Assets:FIXME
default-plus-account: Expenses:FIXME
default-currency: CNY

alipay:
  rules: []

wechat:
  rules: []
"""


config_app = typer.Typer(help="创建和检查 Fane YAML 配置。", no_args_is_help=True)


@config_app.command("init")
def initialize(
    ctx: typer.Context,
    force: Annotated[
        bool, typer.Option("--force", help="覆盖已经存在的配置文件")
    ] = False,
):
    """创建一份可直接修改的最小配置。"""
    with command_errors("配置初始化失败"):
        target = get_cli_context(ctx).config_path
        if target.exists() and not force:
            raise ValueError(f"配置文件已存在，未覆盖: {target}；覆盖需 --force")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(DEFAULT_CONFIG, encoding="utf-8")
        typer.echo(f"已创建配置文件: {target}")


@config_app.command("check")
def check(
    ctx: typer.Context,
    strict: Annotated[
        bool, typer.Option("--strict", help="兼容性警告也视为失败")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 诊断报告")] = False,
):
    """检查配置、规则和关联路径；不修改文件。"""
    report = diagnose_config(
        get_cli_context(ctx).config_path,
        supported_providers=tuple(
            name
            for name in ("alipay", "wechat")
            if (
                Path(__file__).parents[1] / "bill/providers" / name / "reader.py"
            ).is_file()
        ),
    )
    if as_json:
        output_json(
            {
                "config": str(report.config_path),
                "errors": report.errors,
                "warnings": report.warnings,
                "info": report.info,
            }
        )
    else:
        typer.echo(f"配置: {report.config_path}")
        for label, messages in (
            ("信息", report.info),
            ("警告", report.warnings),
            ("错误", report.errors),
        ):
            for message in messages:
                typer.echo(f"[{label}] {message}", err=label == "错误")
        typer.echo(
            f"检查完成: {len(report.errors)} 个错误, {len(report.warnings)} 个警告"
        )
    if report.errors or (strict and report.warnings):
        raise typer.Exit(1)
