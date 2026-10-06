from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

from fane.shared.config import Config, load_config_model
from fane.shared.config.ledger import resolve_context
from fane.shared.config.loader import DEFAULT_CONFIG_PATH
from fane.shared.errors import ConfigError


@dataclass
class CliContext:
    """Configuration belongs to one command invocation."""

    config_path: Path
    _config: Config | None = field(default=None, init=False)

    @property
    def config(self) -> Config:
        if self._config is None:
            try:
                self._config = load_config_model(self.config_path)
            except ConfigError as error:
                typer.echo(f"配置出错: {error}", err=True)
                raise typer.Exit(code=1) from error
        return self._config


def get_cli_context(ctx: typer.Context) -> CliContext:
    return ctx.find_root().obj


LedgerOption = Annotated[
    Path | None,
    typer.Option("--ledger", help="账本入口；也可用 FANE_LEDGER 或配置 ledger.file"),
]


@contextmanager
def errors():
    try:
        yield
    except typer.Exit:
        raise
    except (ValueError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1)


def context(ledger, cli_ctx: typer.Context):
    config = get_cli_context(cli_ctx).config_path
    if config != DEFAULT_CONFIG_PATH and not config.is_file():
        raise ValueError(f"Config does not exist: {config}")
    return resolve_context(ledger, config)
