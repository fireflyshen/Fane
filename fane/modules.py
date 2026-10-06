"""A small lazy command registry. Features depend only on shared contracts."""

import os
from importlib import import_module
from pathlib import Path

from typer.core import TyperGroup
from typer.main import get_command

FEATURES = ("bill", "classify", "subscriptions", "ledger", "query", "flow")
COMMANDS = {
    "flow": ("flow", "fane.flow.cli", "flow", "账单、同步与月报自动化"),
    "bill": ("bill", "fane.bill.cli", "bill", "账单转换与同步"),
    "convert": ("bill", "fane.bill.cli", "bill/convert", "转换账单"),
    "ingest": ("bill", "fane.bill.cli", "bill/ingest", "导入 JSONL，可接管道"),
    "trans": ("bill", "fane.bill.cli", "trans", ""),
    "inspect": ("bill", "fane.bill.cli", "inspect", ""),
    "import": ("bill", "fane.bill.cli", "import", ""),
    "sync": ("bill", "fane.bill.cli", "sync", ""),
    "classify": ("classify", "fane.classify.cli", "classify", "分类决策"),
    "subscriptions": (
        "subscriptions",
        "fane.subscriptions.cli",
        "subscriptions",
        "订阅计划与分录",
    ),
    "sub": (
        "subscriptions",
        "fane.subscriptions.cli",
        "subscriptions",
        "订阅命令的短入口",
    ),
    "ledger": ("ledger", "fane.ledger.cli", "ledger", "账本管理"),
    "query": ("query", "fane.query.cli", "query/run", "按日期查询账本，输出 JSON"),
    "serve": ("query", "fane.query.cli", "query/serve", "启动账本查询 HTTP 服务"),
    "config": (None, "fane.shared.settings", "config", "配置"),
    "init": (None, "fane.shared.setup", "init", ""),
    "doctor": (None, "fane.shared.setup", "doctor", ""),
    "providers": (None, "fane.shared.catalog", "providers", "账单来源"),
    "template": (None, "fane.shared.catalog", "template", "模板"),
}


def installed_modules():
    selected = os.environ.get("FANE_MODULES")
    enabled = set(selected.split(",")) if selected is not None else set(FEATURES)
    root = Path(__file__).parent
    return tuple(
        name
        for name in FEATURES
        if name in enabled and (root / name / "cli.py").is_file()
    )


def provider_names():
    root = Path(__file__).parent / "bill" / "providers"
    return tuple(
        name for name in ("alipay", "wechat") if (root / name / "reader.py").is_file()
    )


class Deferred(TyperGroup):
    def __init__(self, name, definition):
        self.definition = definition
        super().__init__(name=name, help=definition[3], hidden=not definition[3])

    def make_context(self, info_name, args, parent=None, **extra):
        from fane.cli import app

        import_module(self.definition[1])
        command = get_command(app)
        for part in self.definition[2].split("/"):
            command = command.commands[part]
        return command.make_context(info_name, args, parent=parent, **extra)


class ModuleGroup(TyperGroup):
    def list_commands(self, ctx):
        installed = installed_modules()
        return list(
            dict.fromkeys(
                [
                    *(
                        name
                        for name in super().list_commands(ctx)
                        if name not in COMMANDS
                        or COMMANDS[name][0] is None
                        or COMMANDS[name][0] in installed
                    ),
                    *(
                        name
                        for name, definition in COMMANDS.items()
                        if definition[0] is None or definition[0] in installed
                    ),
                ]
            )
        )

    def get_command(self, ctx, cmd_name):
        definition = COMMANDS.get(cmd_name)
        if definition:
            if definition[0] is not None and definition[0] not in installed_modules():
                ctx.fail(f"模块未安装或未启用: {definition[0]}")
            return Deferred(cmd_name, definition)
        return super().get_command(ctx, cmd_name)
