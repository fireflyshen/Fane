from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from fane import cli as root
from fane.shared.config.ledger import resolve_context

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
    config = root.get_cli_context(cli_ctx).config_path
    if config != root.config_file and not config.is_file():
        raise ValueError(f"Config does not exist: {config}")
    return resolve_context(ledger, config)
