import traceback
from pathlib import Path

import typer
from typing_extensions import Annotated

from package.compiler.compiler import Compiler
from package.config import get_config_model
from package.errors import FaneError
from package.parser.analyser import create_analyser
from package.strategy.template.normal import NormalStrategy
from provider.registry import create_provider, supported_provider_names
from .root import app


@app.command()
def trans(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Bills provider")
    ] = "alipay",
    source: Annotated[str, typer.Option("--source", "-s", help="source file")] = "",
) -> None:
    try:
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
        s = p.translate(source)
        config = get_config_model()
        Compiler(provider, config, s, NormalStrategy(), analyser).compile()
    except FaneError as e:
        typer.echo(f"编译出错: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)
