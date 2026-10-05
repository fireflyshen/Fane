import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import (
    BaseLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    Template,
    TemplateNotFound,
    TemplateSyntaxError,
)
from jinja2.exceptions import TemplateError as JinjaError

from fane.core.errors import TemplateError

template_dir = Path(__file__).resolve().parent


def _format_amount(value: Decimal, precision: int | None = 2) -> str:
    return format(value, "f" if precision is None else f".{precision}f")


def _create_environment(loader: BaseLoader) -> Environment:
    environment = Environment(loader=loader, undefined=StrictUndefined)
    environment.filters["bean_quote"] = lambda value: json.dumps(
        str(value), ensure_ascii=False
    )
    environment.filters["amount"] = _format_amount
    return environment


env = _create_environment(PackageLoader("fane.infrastructure.rendering", package_path=""))


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
    amount_precision: int | None = 2


def _environment(file: Path | None = None) -> tuple[Environment, str | None]:
    if file is None:
        return env, None
    file = file.expanduser().resolve()
    if not file.is_file():
        raise TemplateError(f"模板文件不存在: {file}")
    return _create_environment(FileSystemLoader(str(file.parent))), file.name


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


def render_normal_order(
    order: NormalOrder,
    *,
    template_name: str = "normal.j2",
    template_file: Path | None = None,
) -> str:
    template = get_template(template_name, template_file)
    try:
        return template.render(**vars(order))
    except JinjaError as error:
        raise TemplateError(
            f"模板渲染失败: {error}；可用变量见 fa template fields"
        ) from error


def template_names() -> list[str]:
    return env.list_templates(filter_func=lambda name: name.endswith(".j2"))


def template_source(name: str = "normal.j2", file: Path | None = None) -> str:
    environment, filename = _environment(file)
    try:
        return environment.loader.get_source(environment, filename or name)[0]
    except TemplateNotFound as error:
        raise TemplateError(f"模板不存在: {filename or name}") from error
