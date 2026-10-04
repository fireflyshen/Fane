from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    Template,
    TemplateNotFound,
    TemplateSyntaxError,
)

from fane.core.errors import TemplateError

template_dir = Path(__file__).resolve().parent
# 初始化
env: Environment = Environment(
    loader=PackageLoader("fane.infrastructure.rendering", package_path=""),
    undefined=StrictUndefined,
)


@dataclass
class NormalOrder:
    pay_time: Optional[datetime]
    peer: Optional[str]
    item: str
    note: str
    money: Decimal
    commission: Decimal
    plus_account: str
    minus_account: str
    plus_str: str
    minus_str: str
    pnl_account: str
    commission_account: str
    currency: str
    metadata: dict[str, str]
    tags: list[str]


def _environment(file: Path | None = None) -> tuple[Environment, str | None]:
    if file is None:
        return env, None
    file = file.expanduser().resolve()
    if not file.is_file():
        raise TemplateError(f"模板文件不存在: {file}")
    return Environment(
        loader=FileSystemLoader(str(file.parent)), undefined=StrictUndefined
    ), file.name


def get_template(
    template_name: str = "normal.j2", file: Path | None = None
) -> Template:
    environment, filename = _environment(file)
    try:
        return environment.get_template(filename or template_name)
    except TemplateNotFound as error:
        raise TemplateError(
            f"模板缺失: {filename or template_name}；内置模板随 Fane 安装，请重新安装或指定 --template"
        ) from error
    except TemplateSyntaxError as error:
        raise TemplateError(
            f"模板语法错误: {error.name}:{error.lineno}: {error.message}"
        ) from error


def template_names() -> list[str]:
    return env.list_templates(filter_func=lambda name: name.endswith(".j2"))


def template_source(name: str = "normal.j2", file: Path | None = None) -> str:
    environment, filename = _environment(file)
    try:
        return environment.loader.get_source(environment, filename or name)[0]
    except TemplateNotFound as error:
        raise TemplateError(f"模板不存在: {filename or name}") from error
