from dataclasses import fields
from pathlib import Path
from typing import Annotated

import typer

from fane.bootstrap import supported_provider_names
from fane.infrastructure.rendering.templates import (
    NormalOrder,
    get_template,
    template_names,
    template_source,
)

from .common import command_errors, output_json, output_text
from .root import app

providers_app = typer.Typer(help="查看支持的账单来源。", no_args_is_help=True)
template_app = typer.Typer(
    help="查看、导出和检查 Beancount Jinja2 模板。", no_args_is_help=True
)
app.add_typer(providers_app, name="providers")
app.add_typer(template_app, name="template")


@providers_app.command("list")
def providers(
    as_json: Annotated[bool, typer.Option("--json", help="JSON 来源名称列表")] = False,
):
    names = list(supported_provider_names())
    output_json(names) if as_json else output_text("\n".join(names))


@template_app.command("list")
def templates(
    as_json: Annotated[
        bool, typer.Option("--json", help="JSON 内置模板名称列表")
    ] = False,
):
    with command_errors("模板读取失败"):
        names = template_names()
        output_json(names) if as_json else output_text("\n".join(names))


@template_app.command("show")
def show(
    name: Annotated[str, typer.Option("--name", help="内置模板名称")] = "normal.j2",
    file: Annotated[
        Path | None, typer.Option("--file", help="改为读取外部模板文件")
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="输出文件；默认 stdout，可用于导出模板"),
    ] = "-",
):
    """显示模板原文，或用 --output 导出后修改。"""
    with command_errors("模板读取失败"):
        output_text(template_source(name, file), output)


@template_app.command("check")
def check(
    name: Annotated[str, typer.Option("--name", help="内置模板名称")] = "normal.j2",
    file: Annotated[
        Path | None, typer.Option("--file", help="检查外部模板文件")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 检查报告")] = False,
):
    """检查模板存在且 Jinja2 语法可编译；不修改文件。"""
    with command_errors("模板检查失败"):
        get_template(name, file)
        result = {"status": "valid", "template": str(file) if file else name}
        output_json(result) if as_json else output_text(
            f"模板语法有效: {result['template']}"
        )


@template_app.command("fields")
def template_fields(
    as_json: Annotated[bool, typer.Option("--json", help="JSON 模板变量列表")] = False,
):
    """列出可以在模板中使用的变量和类型。"""
    rows = [
        {"name": field.name, "type": str(field.type)} for field in fields(NormalOrder)
    ]
    output_json(rows) if as_json else output_text(
        "\n".join(f"{row['name']}: {row['type']}" for row in rows)
    )
