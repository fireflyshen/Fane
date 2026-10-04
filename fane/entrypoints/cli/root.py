import re
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from typing_extensions import Annotated

from fane.bootstrap import build_converter
from fane.config import Config, load_config_model
from fane.core.conversion import ConversionService
from fane.core.errors import ConfigError

app = typer.Typer(
    help="Fane：账单转换、账本管理、分类、订阅与模板。",
    no_args_is_help=True,
)
config_file = Path().home() / ".flow" / "config.yaml"


def _source_version() -> str | None:
    """Read the version in a source checkout without adding a TOML dependency."""
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
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


@dataclass
class CliContext:
    """One invocation owns its configuration and wired services."""

    config_path: Path
    _config: Config | None = field(default=None, init=False)
    _converter: ConversionService | None = field(default=None, init=False)

    @property
    def config(self) -> Config:
        if self._config is None:
            try:
                self._config = load_config_model(self.config_path)
            except ConfigError as error:
                typer.echo(f"配置出错: {error}", err=True)
                raise typer.Exit(code=1) from error
        return self._config

    @property
    def converter(self) -> ConversionService:
        if self._converter is None:
            self._converter = build_converter(self.config)
        return self._converter


def get_cli_context(ctx: typer.Context) -> CliContext:
    return ctx.find_root().obj


@app.callback()
def initialize(
    ctx: typer.Context,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Fane YAML 配置；全局选项，放在命令组之前",
            envvar="FANE_CONFIG",
        ),
    ] = str(config_file),
    toogle: Annotated[bool, typer.Option("--toggle", "-t", hidden=True)] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-v", is_eager=True, callback=version_callback, help="version"
        ),
    ] = False,
) -> None:
    ctx.obj = CliContext(Path(config).expanduser())
