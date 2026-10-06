"""Project-owned commands for n8n; no executable code in the data directory."""

import base64
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from fane.shared.context import get_cli_context

flow = typer.Typer(
    help="组合账单、账本同步与报告；不启动额外服务。", no_args_is_help=True
)


@flow.callback()
def initialize(
    ctx: typer.Context,
    root: Annotated[
        Path, typer.Option(envvar="FANE_FLOW_ROOT", help="配置、数据和状态目录")
    ] = Path.home() / ".flow",
):
    os.umask(0o077)
    ctx.obj = root.expanduser().resolve()


def emit(value):
    typer.echo(json.dumps(value, ensure_ascii=False))


def request(encoded):
    value = (
        json.loads(base64.b64decode(encoded, validate=True))
        if encoded
        else json.load(sys.stdin)
    )
    if not isinstance(value, dict):
        raise ValueError("Request must be an object")
    return value


def lock(root):
    path = root / "state/locks/n8n-finance.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a")


@flow.command("bill")
def bill_command(
    ctx: typer.Context,
    operation: str,
    payload: Annotated[str, typer.Argument()] = "",
    preview: bool = False,
):
    """prepare：解压、入账并提取分类；finish：应用分类与生成订阅。"""
    from .bill import BillFlow

    root = ctx.obj
    configured = get_cli_context(ctx).config_path
    bill = BillFlow(
        root, configured if configured.is_file() else root / "config/fane.yaml"
    )
    if operation not in ("prepare", "finish"):
        raise typer.BadParameter("Use prepare or finish")
    meta = (
        request(payload)
        if operation == "prepare"
        else {"decisions_b64": payload, "preview": preview}
    )
    with lock(root) as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        emit(getattr(bill, operation)(meta))


@flow.command("report")
def report_command(
    ctx: typer.Context,
    operation: str,
    request_base64: Annotated[
        str, typer.Option(help="不提供时从 stdin 读取 JSON")
    ] = "",
    dry_run: bool = False,
):
    """notice / plan / prepare / store / begin / sent / release / bootstrap。"""
    from .report import Reports

    reports = Reports(root=ctx.obj)
    try:
        if operation in ("notice", "plan"):
            result = getattr(reports, operation)(dry_run)
        elif operation == "bootstrap":
            result = reports.bootstrap(
                request(request_base64) if request_base64 else None
            )
        elif operation in ("prepare", "store", "begin", "sent", "release"):
            result = getattr(reports, operation)(request(request_base64))
        else:
            raise typer.BadParameter("Unknown report operation")
        emit(result)
    finally:
        reports.db.close()


@flow.command("sync")
def sync_command(ctx: typer.Context, payload: Annotated[str, typer.Argument()] = ""):
    """校验 GitHub 原始请求签名并同步账本；JSON 可从 stdin 输入。"""
    from . import sync

    config = json.loads((ctx.obj / "config/n8n-sync.json").read_text())
    status, message = sync.handle(request(payload), config, root=ctx.obj)
    emit({"status": status, "message": message, "report": message == "Deploy success"})


@flow.command("commit")
def commit_command(ctx: typer.Context):
    """提交入账结果，推送既有账本仓库，并通知月报检查。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .report import Reports

    with lock(ctx.obj) as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        repository = ctx.obj / "data/account"

        def run(*args, check=True):
            return subprocess.run(
                ["git", *args],
                cwd=repository,
                capture_output=True,
                check=check,
                timeout=180,
            )

        run("add", "--all")
        status = run("diff", "--cached", "--quiet", check=False).returncode
        if status == 1:
            run(
                "commit",
                "-m",
                "账单更新 "
                + datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            )
        elif status:
            raise RuntimeError("Cannot inspect ledger changes")
        run("push")
        reports = Reports(root=ctx.obj)
        try:
            emit(reports.notice())
        finally:
            reports.db.close()
