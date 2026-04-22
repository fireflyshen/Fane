from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import FileSystemLoader, Environment

base_dir = Path(__file__).parent.parent.resolve()
template_dir = base_dir / "template"
# 初始化
env = Environment(loader=FileSystemLoader(str(template_dir)))


@dataclass
class NormalOrder:
    pay_time: Optional[datetime]
    peer: Optional[str]
    item: Optional[str]
    note: Optional[str]
    money: Optional[Decimal]
    commission: Optional[Decimal]
    plus_account: Optional[str]
    minus_account: Optional[str]
    plus_str: Optional[str]
    minus_str: Optional[str]
    pnl_account: Optional[str]
    commission_account: Optional[str]
    currency: Optional[str]
    metadata: Optional[dict[str, str]]
    tags: Optional[list[str]]


def get_template(template_name: str):
    return env.get_template(f"{template_name}")
