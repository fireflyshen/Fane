"""CLI and HTTP share the same read-only query contract."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from fane.shared.context import LedgerOption, context
from fane.shared.output import command_errors, output_json


def query(
    ctx: typer.Context,
    start: Annotated[str | None, typer.Argument(help="起始日期 YYYY-MM-DD")] = None,
    end: Annotated[str | None, typer.Argument(help="结束日期 YYYY-MM-DD")] = None,
    ledger: LedgerOption = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=500)] = 500,
    input_file: Annotated[
        str | None, typer.Option("--input", "-i", help="JSON 请求文件；- 读取 stdin")
    ] = None,
    output: Annotated[str, typer.Option("--output", "-o")] = "-",
):
    """输出含收支、转账及交易明细的 JSON；支持管道输入。"""
    from .engine import BeancountQuery
    from .service import LedgerService

    with command_errors("查询失败"):
        if input_file is not None:
            if start is not None or end is not None:
                raise ValueError("日期参数与 --input 只能选一种")
            payload = json.loads(
                sys.stdin.read() if input_file == "-" else Path(input_file).read_text()
            )
        else:
            payload = {"start_date": start, "end_date": end, "max_transactions": limit}
        output_json(
            LedgerService(BeancountQuery(context(ledger, ctx).ledger)).execute(payload),
            output,
        )


def serve(
    ctx: typer.Context,
    ledger: LedgerOption = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8080,
):
    """GET /health、POST /query；读取账本，接口与 ledger-query 兼容。"""
    from .engine import BeancountQuery
    from .http import create_server
    from .http import serve as run
    from .service import LedgerService

    with command_errors("服务启动失败"):
        run(
            create_server(
                host,
                port,
                query=LedgerService(BeancountQuery(context(ledger, ctx).ledger)),
            )
        )
