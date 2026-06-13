from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import typer
from typing_extensions import Annotated

import package.config.init as cfg
from package.errors import ConfigError

cfg_file: str = None
app = typer.Typer(help="fflow")
config_file = Path().home() / ".flow" / "bill.yaml"


def version_callback(value: bool):
    if value:
        try:
            pkg_version = version("bill-flow-enmu")
            print(f"Task Flow Version: {pkg_version}")
        except PackageNotFoundError:
            print("Task Flow Version: Unknown (Package not installed)")

        raise typer.Exit()


@app.callback()
def initialize(
        ctx: typer.Context,
        config: Annotated[
            Path,
            typer.Option(
                "--config",
                "-c",
                help="config file (default is $HOME/.double-entry-generator.yaml)",
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
):
    if ctx.invoked_subcommand == "version":
        return
    global cfg_file
    cfg_file = str(config)
    try:
        cfg.init_config(cfg_file)
    except ConfigError as ce:
        typer.echo(f"配置出错: {ce}", err=True)
        raise typer.Exit(code=1)
