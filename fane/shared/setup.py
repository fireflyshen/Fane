from pathlib import Path

import typer
from typing_extensions import Annotated

from fane.cli import root
from fane.modules import provider_names as supported_provider_names
from fane.shared.config.diagnostics import diagnose_config

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


def _configured_path(ctx: typer.Context) -> Path:
    return root.get_cli_context(ctx).config_path


@root.app.command("init", hidden=True)
def init_config(
    ctx: typer.Context,
    force: Annotated[
        bool,
        typer.Option("--force", help="覆盖已经存在的配置文件"),
    ] = False,
) -> None:
    """创建一份可直接修改的最小配置。"""
    target = _configured_path(ctx)
    if target.exists() and not force:
        typer.echo(f"配置文件已存在，未覆盖: {target}", err=True)
        typer.echo("如需覆盖，请显式使用 --force", err=True)
        raise typer.Exit(code=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG, encoding="utf-8")
    typer.echo(f"已创建配置文件: {target}")
    typer.echo(f"下一步: fa --config {target} config check")


@root.app.command("doctor", hidden=True)
def doctor(
    ctx: typer.Context,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="发现警告时也返回失败状态"),
    ] = False,
) -> None:
    """检查配置结构、规则和关联账本路径，不转换或写入账单。"""
    report = diagnose_config(
        _configured_path(ctx), supported_providers=supported_provider_names()
    )
    typer.echo(f"配置: {report.config_path}")
    for message in report.info:
        typer.echo(f"[信息] {message}")
    for message in report.warnings:
        typer.echo(f"[警告] {message}")
    for message in report.errors:
        typer.echo(f"[错误] {message}", err=True)
    typer.echo(f"检查完成: {len(report.errors)} 个错误, {len(report.warnings)} 个警告")
    if report.errors or (strict and report.warnings):
        raise typer.Exit(code=1)
