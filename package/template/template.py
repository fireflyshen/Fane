from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, Template

base_dir = Path(__file__).parent.parent.resolve()
template_dir = base_dir / "template"
# 初始化
env: Environment = Environment(loader=FileSystemLoader(str(template_dir)))


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


def get_template(template_name: str) -> Template:
    return env.get_template(f"{template_name}")
