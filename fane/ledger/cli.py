"""Thin CLI adapters for the ledger services."""

import subprocess
from datetime import date, timedelta
from pathlib import Path

import typer
from typing_extensions import Annotated

from fane.shared.context import LedgerOption, context, errors
from fane.version import get_version

app = typer.Typer(help="校验账本、生成余额断言、导出和发布快照。", no_args_is_help=True)


@app.command("validate")
def validate(
    cli_ctx: typer.Context,
    ledger: LedgerOption = None,
    allow: Annotated[
        list[str] | None,
        typer.Option(
            "--allow-ambiguous-account", help="允许指定账户含策略禁止的段名；可重复"
        ),
    ] = None,
):
    """只读校验；失败返回非零退出码。"""
    from fane.shared.check import validate_ledger

    with errors():
        ctx = context(ledger, cli_ctx)
        failures = validate_ledger(
            ctx.ledger, ctx.settings.policy, ctx.config, allow or ()
        )
        if failures:
            typer.echo("Ledger validation failed.", err=True)
            for failure in failures:
                typer.echo(failure, err=True)
            raise typer.Exit(1)
        typer.echo("Ledger validation passed.")


@app.command("assertions")
def assertions(
    cli_ctx: typer.Context,
    ledger: LedgerOption = None,
    cutoff: Annotated[
        str | None, typer.Option("--date", help="断言日初余额，YYYY-MM-DD；默认明天")
    ] = None,
    write: Annotated[
        bool, typer.Option("--write", help="写入输出文件并更新 include；默认仅预览")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", help="断言文件；相对主账本目录")
    ] = None,
    index: Annotated[
        Path | None,
        typer.Option("--index", help="写入 include 的索引文件；相对主账本目录"),
    ] = None,
    include_internal: Annotated[
        bool,
        typer.Option("--include-internal", help="包含 ignored-prefixes 排除的账户"),
    ] = False,
    precision: Annotated[
        int | None,
        typer.Option("--precision", min=0, help="小数位数；默认配置值，未配置时为 2"),
    ] = None,
):
    """预览资产/负债账户的日初余额断言；--write 才写文件及 include。"""
    from fane.ledger.assertions import (
        calculate_balances,
        render_assertions,
        write_assertions,
    )

    with errors():
        ctx = context(ledger, cli_ctx)
        settings = ctx.settings.assertions
        day = date.fromisoformat(cutoff) if cutoff else date.today() + timedelta(days=1)
        balances = calculate_balances(
            ctx.ledger, day, include_internal, settings.ignored_prefixes
        )
        text = render_assertions(
            balances, day, settings.precision if precision is None else precision
        )
        if not write:
            typer.echo(text, nl=False)
            return
        if output is None:
            if not settings.output_dir:
                raise ValueError(
                    "Writing requires --output or ledger.assertions.output-dir"
                )
            output = Path(settings.output_dir) / settings.filename_template.format(
                date=day
            )
        index = index or settings.index
        if not index:
            raise ValueError("Writing requires --index or ledger.assertions.index")
        target = ctx.output_path(output)
        destination = ctx.output_path(index)
        if target == destination:
            raise ValueError("Assertion output and index must be different files")
        write_assertions(target, destination, text)
        typer.echo(f"Wrote {len(balances)} assertions to {target}")


@app.command("export")
def export(
    cli_ctx: typer.Context,
    ledger: LedgerOption = None,
    year: Annotated[
        int | None,
        typer.Option(
            "--year", min=1, max=9999, help="仅导出指定年份；与 --meta/--all 互斥"
        ),
    ] = None,
    meta: Annotated[
        bool, typer.Option("--meta", help="只导出元信息；与 --year/--all 互斥")
    ] = False,
    all_years: Annotated[
        bool, typer.Option("--all", help="显式导出所有年份（也是默认行为）")
    ] = False,
    version: Annotated[
        str, typer.Option("--version", envvar="GITHUB_SHA", help="快照的源账本版本标识")
    ] = "local",
    transactions: Annotated[
        bool,
        typer.Option("--include-transactions", help="附加交易明细，移除文件名和行号"),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="JSON 文件；默认 stdout，相对路径按当前目录"),
    ] = None,
):
    """导出 JSON；默认所有年份。交易明细移除账本文件名和行号。"""
    from fane.ledger.snapshot import export_snapshot, write_json

    with errors():
        if sum((year is not None, meta, all_years)) > 1:
            raise ValueError("Choose only one of --year, --meta, --all")
        ctx = context(ledger, cli_ctx)
        payload = export_snapshot(
            ctx.ledger,
            year=year,
            meta=meta,
            version=version,
            include_transactions=transactions,
            accrual_prefixes=ctx.settings.snapshot.accrual_offset_prefixes,
        )
        write_json(payload, output)


@app.command("serve")
def serve(
    cli_ctx: typer.Context,
    ledger: LedgerOption = None,
    executable: Annotated[
        str | None,
        typer.Option(
            "--executable", envvar="FAVA_EXECUTABLE", help="外部 Fava 可执行文件路径"
        ),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="监听地址")] = "127.0.0.1",
    port: Annotated[
        int, typer.Option("--port", min=1, max=65535, help="监听端口")
    ] = 5000,
):
    """使用已安装的 Fava 打开账本。"""
    with errors():
        ctx = context(ledger, cli_ctx)
        args = ["--host", host, "--port", str(port), str(ctx.ledger)]
        if executable:
            result = subprocess.run([executable, *args])
            raise typer.Exit(result.returncode)
        from importlib.metadata import entry_points

        installed = list(entry_points(group="console_scripts", name="fava"))
        if not installed:
            raise ValueError("Install Fane with the web extra, or specify --executable")
        installed[0].load()(args=args, standalone_mode=False)


@app.command("publish")
def publish(
    cli_ctx: typer.Context,
    version: Annotated[str, typer.Option("--version", help="源账本提交 SHA")],
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", envvar="FANE_R2_ENDPOINT", help="R2 的 S3 API 地址"),
    ],
    bucket: Annotated[
        str, typer.Option("--bucket", envvar="FANE_R2_BUCKET", help="目标存储桶名称")
    ],
    ledger: LedgerOption = None,
    key: Annotated[
        str, typer.Option("--key", envvar="FANE_R2_KEY", help="当前快照指针的对象名")
    ] = "current.json",
    force: Annotated[bool, typer.Option("--force", help="相同版本也重新发布")] = False,
    generator_version: Annotated[
        str | None,
        typer.Option("--generator-version", help="覆盖生成器版本；默认 Fane 版本"),
    ] = None,
):
    """校验并原子发布 R2 快照；相同账本及工具版本自动跳过。凭据用 AWS 环境变量。"""
    from fane.ledger.publishing import publish_snapshot

    try:
        import boto3
    except ImportError:
        typer.echo(
            'Install Fane with the cloud extra: pip install "Fane[cloud]"', err=True
        )
        raise typer.Exit(1)
    with errors():
        ctx = context(ledger, cli_ctx)
        try:
            changed = publish_snapshot(
                boto3.client("s3", endpoint_url=endpoint, region_name="auto"),
                ledger=ctx.ledger,
                policy=ctx.settings.policy,
                config=ctx.config,
                bucket=bucket,
                key=key,
                version=version,
                generator_version=generator_version or get_version(),
                force=force,
                accrual_prefixes=ctx.settings.snapshot.accrual_offset_prefixes,
            )
        except ValueError:
            raise
        except Exception:
            typer.echo(
                "R2 operation failed; check credentials, endpoint and bucket. Existing snapshot was not intentionally deleted.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo("Snapshot published." if changed else "Snapshot unchanged; skipped.")
