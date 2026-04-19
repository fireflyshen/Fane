import typer
from .root import app
from package.config import get_config, Config
from typing_extensions import Annotated
from provider.provider import get_provider
from package.compiler.compiler import Compiler
from package.strategy.template.normal import NormalStrategy
from package.parser.paser import get_analyser
import traceback


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
        s = p.translate(source)
        config_content = get_config()
        config = Config.model_validate(config_content)
        Compiler(
            provider, config, s, NormalStrategy(), get_analyser(provider)
        ).compile()
    except Exception as e:
        typer.echo(f"编译出错: {e}")
        traceback.print_exc()
