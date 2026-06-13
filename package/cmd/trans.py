import traceback
from pathlib import Path

import typer
from typing_extensions import Annotated

from package.compiler.compiler import Compiler
from package.config import get_config, Config
from package.errors import FaneError
from package.parser.paser import get_analyser
from package.strategy.template.normal import NormalStrategy
from provider.provider import get_provider
from .root import app


@app.command()
def trans(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Bills provder")
    ] = "alipay",
    source: Annotated[str, typer.Option("--source", "-s", help="source file")] = "",
):
    try:
        p = get_provider(provider)
        if p is None:
            typer.echo(f"不支持的 provider: {provider}，可选属有: alipay, wechat")
            raise typer.Exit(code=1)
        if not source:
            typer.echo("请通过 --source/-s 指定账单文件", err=True)
            raise typer.Exit(code=1)
        if not Path(source).is_file():
            typer.echo(f"账单文件不存在: {source}", err=True)
            raise typer.Exit(code=1)
        analyser = get_analyser(provider)
        if analyser is None:
            typer.echo(f"不支持的 analyser: {provider}", err=True)
            raise typer.Exit(code=1)
        s = p.translate(source)
        config_content = get_config()
        config = Config.model_validate(config_content)
        Compiler(
            provider, config, s, NormalStrategy(), analyser
        ).compile()
    except FaneError as e:
        typer.echo(f"编译出错: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"编译出错: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)
    
