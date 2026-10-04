from typing import Annotated

import typer

from fane.bootstrap import supported_provider_names
from fane.config.diagnostics import diagnose_config

from .common import command_errors, output_json
from .root import app, get_cli_context
from .setup import doctor, init_config

config_app = typer.Typer(help="创建和检查 Fane YAML 配置。", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("init")
def initialize(
    ctx: typer.Context,
    force: Annotated[
        bool, typer.Option("--force", help="覆盖已经存在的配置文件")
    ] = False,
):
    """创建一份可直接修改的最小配置。"""
    with command_errors("配置初始化失败"):
        init_config(ctx, force)


@config_app.command("check")
def check(
    ctx: typer.Context,
    strict: Annotated[
        bool, typer.Option("--strict", help="兼容性警告也视为失败")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 诊断报告")] = False,
):
    """检查配置、规则和关联路径；不修改文件。"""
    if not as_json:
        doctor(ctx, strict)
        return
    report = diagnose_config(
        get_cli_context(ctx).config_path, supported_providers=supported_provider_names()
    )
    output_json(
        {
            "config": str(report.config_path),
            "errors": report.errors,
            "warnings": report.warnings,
            "info": report.info,
        }
    )
    if report.errors or (strict and report.warnings):
        raise typer.Exit(1)
