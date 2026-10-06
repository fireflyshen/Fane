from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from typing_extensions import Annotated

from fane.modules import ModuleGroup

if TYPE_CHECKING:
    from fane.shared.config import Config
    from fane.shared.conversion import ConversionService

app = typer.Typer(
    help="Fane：账单转换、账本管理、分类、订阅与模板。",
    no_args_is_help=True,
    cls=ModuleGroup,
)
config_file = Path().home() / ".flow" / "config.yaml"


def _source_version() -> str | None:
    """Read the version in a source checkout without adding a TOML dependency."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
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
            from fane.shared.config import load_config_model
            from fane.shared.errors import ConfigError

            try:
                self._config = load_config_model(self.config_path)
            except ConfigError as error:
                typer.echo(f"配置出错: {error}", err=True)
                raise typer.Exit(code=1) from error
        return self._config

    @property
    def converter(self) -> ConversionService:
        if self._converter is None:
            from fane.bill.build import build_converter

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


def __getattr__(name):
    # Historical Python entrypoints stay available without eager imports.
    from importlib import import_module

    paths = {
        "root": "fane.cli",
        "setup": "fane.shared.setup",
        "sync": "fane.bill.jobs",
        "trans": "fane.bill.legacy",
        "ledger": "fane.ledger.cli",
        "bill": "fane.bill.cli",
        "catalog": "fane.shared.catalog",
        "classify": "fane.classify.cli",
        "configuration": "fane.shared.settings",
        "subscriptions": "fane.subscriptions.cli",
    }
    if name not in paths:
        raise AttributeError(name)
    return import_module(paths[name])


@app.command("modules")
def list_modules():
    """列出当前安装并启用的独立功能模块。"""
    from fane.modules import installed_modules

    typer.echo("\n".join(installed_modules()))


@app.command("check")
def check(
    ctx: typer.Context,
    ledger: Annotated[Path | None, typer.Option("--ledger", "-l")] = None,
):
    """只读校验账本，与 ledger validate 相同。"""
    from fane.shared.check import validate_ledger
    from fane.shared.context import context

    location = context(ledger, ctx)
    failures = validate_ledger(
        location.ledger, location.settings.policy, location.config
    )
    if failures:
        for failure in failures:
            typer.echo(failure, err=True)
        raise typer.Exit(1)
    typer.echo("Ledger validation passed.")
