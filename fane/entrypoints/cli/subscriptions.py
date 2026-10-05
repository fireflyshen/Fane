from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

from fane.application.subscriptions import SubscriptionService

from .common import command_errors, output_json, output_text
from .ledger import LedgerOption, context
from .root import app, get_cli_context

subscriptions_app = typer.Typer(
    help="创建订阅计划、检查账户和生成月度分录。", no_args_is_help=True
)
app.add_typer(subscriptions_app, name="subscriptions")
SubscriptionsOption = Annotated[
    Path | None,
    typer.Option(
        "--subscriptions", help="订阅 JSON；默认 Fane YAML 同目录的 subscriptions.json"
    ),
]


def _plan_path(ctx: typer.Context, plan: Path | None) -> Path:
    return (
        (plan or get_cli_context(ctx).config_path.with_name("subscriptions.json"))
        .expanduser()
        .resolve()
    )


def _service(
    ctx: typer.Context, ledger: Path | None, plan: Path | None
) -> SubscriptionService:
    return SubscriptionService(context(ledger, ctx).ledger, _plan_path(ctx, plan))


@subscriptions_app.command("init")
def initialize(
    ctx: typer.Context,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="订阅 JSON 的创建位置")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="覆盖已有计划文件")] = False,
):
    """创建暂停状态的示例订阅；修改账户并启用后使用。"""
    with command_errors("订阅初始化失败"):
        path = _plan_path(ctx, output)
        if path.exists() and not force:
            raise ValueError(f"订阅计划已存在，未覆盖: {path}；覆盖需 --force")
        output_text(
            files("fane.application")
            .joinpath("subscriptions.example.json")
            .read_text(encoding="utf-8"),
            str(path),
        )
        typer.echo(f"已创建订阅计划: {path}")


@subscriptions_app.command("check")
def check(
    ctx: typer.Context,
    ledger: LedgerOption = None,
    subscriptions: SubscriptionsOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="JSON 检查结果")] = False,
):
    """只读检查计划、账本、账户和币种。"""
    with command_errors("订阅检查失败"):
        result = _service(ctx, ledger, subscriptions).check()
        output_json(result) if as_json else typer.echo(
            f"订阅配置有效，共 {result['subscriptions']} 项"
        )


@subscriptions_app.command("generate")
def generate(
    ctx: typer.Context,
    ledger: LedgerOption = None,
    subscriptions: SubscriptionsOption = None,
    month: Annotated[
        str | None, typer.Option("--month", help="仅生成 YYYY-MM 指定月份")
    ] = None,
    until: Annotated[
        str | None,
        typer.Option("--until", help="从订阅起始日生成到 YYYY-MM-DD；默认本机今天"),
    ] = None,
    write: Annotated[
        bool, typer.Option("--write", help="正式追加分录并更新 include；默认仅预览")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="JSON 结果，包含每笔分录文本")
    ] = False,
    template: Annotated[
        Path | None, typer.Option("--template", help="本次使用的自定义 Jinja2 模板")
    ] = None,
):
    """生成缺少的月度分录；正式写入后检查账本，失败回滚。"""
    with command_errors("订阅生成失败"):
        cli = get_cli_context(ctx)
        if template is None and cli.config_path.is_file() and cli.config.template_file:
            template = Path(cli.config.template_file)
        result = _service(ctx, ledger, subscriptions).generate(
            month=month, until=until, write=write, template_file=template
        )
        if as_json:
            output_json(result)
        else:
            for entry in result["entries"]:
                typer.echo(
                    f"{entry['date']} {entry['subscription_id']} -> {entry['target']}"
                )
            typer.echo(
                f"{result['status']}: 计划 {result['total']} 条，实际写入 {result['written']} 条"
            )
