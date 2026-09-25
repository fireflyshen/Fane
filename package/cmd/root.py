import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from typing_extensions import Annotated

import package.config.init as cfg
from package.errors import ConfigError

cfg_file: str | None = None
app = typer.Typer(
    help="Fane：将支付宝、微信账单转换并导入 Beancount。",
    no_args_is_help=True,
)
config_file = Path().home() / ".flow" / "config.yaml"


def _source_version() -> str | None:
    """Read the version in a source checkout without adding a TOML dependency."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.is_file():
        return None
    match = re.search(
        r'^version\s*=\s*["\']([^"\']+)["\']',
        pyproject.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    return match.group(1) if match else None


def get_version() -> str:
    # ``bill-flow-enmu`` was the historical distribution name. Keep it as a
    # fallback so existing installations remain compatible.
    for distribution in ("Fane", "bill-flow-enmu"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return _source_version() or "Unknown"


def version_callback(value: bool) -> None:
    if value:
        print(f"Fane Version: {get_version()}")
        raise typer.Exit()


def _is_help_request() -> bool:
    return any(arg in {"--help", "-h"} for arg in sys.argv[1:])


@app.callback()
def initialize(
    ctx: typer.Context,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="config file (default is $HOME/.flow/config.yaml)",
        ),
    ] = str(config_file),
    toogle: Annotated[
        bool, typer.Option("--toggle", "-t", help="Help message for toggle")
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-v", is_eager=True, callback=version_callback, help="version"
        ),
    ] = False,
) -> None:
    global cfg_file
    cfg_file = str(config)
    # Help, initialization and diagnostics must work before a config exists.
    # Real conversion commands keep the historical eager-loading behavior.
    if (
        ctx.invoked_subcommand is None
        or ctx.invoked_subcommand in {"init", "doctor"}
        or _is_help_request()
    ):
        return
    try:
        cfg.init_config(cfg_file)
    except ConfigError as ce:
        typer.echo(f"配置出错: {ce}", err=True)
        raise typer.Exit(code=1)
