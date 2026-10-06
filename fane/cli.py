"""Explicit command wiring. Feature modules never import this file."""

from pathlib import Path
from typing import Annotated

import typer

from fane.shared import catalog, settings
from fane.shared.config.loader import DEFAULT_CONFIG_PATH
from fane.shared.context import CliContext, LedgerOption, context
from fane.shared.output import command_errors
from fane.version import get_version

app = typer.Typer(help="Fane：账单、分类、订阅、账本与查询。", no_args_is_help=True)


def version_callback(value: bool):
    if value:
        typer.echo(f"Fane Version: {get_version()}")
        raise typer.Exit()


@app.callback()
def initialize(
    ctx: typer.Context,
    config: Annotated[
        Path,
        typer.Option(
            "--config", "-c", envvar="FANE_CONFIG", help="YAML 配置；放在命令之前"
        ),
    ] = DEFAULT_CONFIG_PATH,
    version: Annotated[
        bool, typer.Option("--version", "-v", is_eager=True, callback=version_callback)
    ] = False,
):
    ctx.obj = CliContext(config.expanduser())


app.add_typer(settings.config_app, name="config")
app.add_typer(catalog.template_app, name="template")


@app.command("check")
def check(ctx: typer.Context, ledger: LedgerOption = None):
    """只读校验账本，失败返回非零退出码。"""
    from fane.shared.check import validate_ledger

    with command_errors("账本校验失败"):
        location = context(ledger, ctx)
        failures = validate_ledger(
            location.ledger, location.settings.policy, location.config
        )
        if failures:
            for failure in failures:
                typer.echo(failure, err=True)
            raise typer.Exit(1)
        typer.echo("Ledger validation passed.")


# Removing a feature removes its commands. No plugin loader or import aliases.
features = Path(__file__).parent
if (features / "bill/cli.py").is_file():
    from fane.bill import cli as bill

    app.add_typer(bill.bill_app, name="bill")
    app.add_typer(bill.providers_app, name="providers")
    app.command("convert")(bill.convert)
    app.command("ingest")(bill.ingest)
if (features / "classify/cli.py").is_file():
    from fane.classify.cli import classify_app

    app.add_typer(classify_app, name="classify")
if (features / "subscriptions/cli.py").is_file():
    from fane.subscriptions.cli import subscriptions_app

    app.add_typer(subscriptions_app, name="subscriptions")
    app.add_typer(subscriptions_app, name="sub")
if (features / "ledger/cli.py").is_file():
    from fane.ledger import cli as ledger

    app.add_typer(ledger.app, name="ledger")
if (features / "query/cli.py").is_file():
    from fane.query import cli as query

    app.command("query")(query.query)
    app.command("serve")(query.serve)
if (features / "flow/cli.py").is_file():
    from fane.flow.cli import flow

    app.add_typer(flow, name="flow")
