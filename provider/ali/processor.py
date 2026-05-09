import json
import logging
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from ir.ir import IR, Order
from provider.ali.ali_types import DealStatus


def post_process(ir: IR) -> IR:
    orders = []

    for o in ir.orders:
        status = o.meta_data.get("status")

        if status == DealStatus.CLOSE.value and o.meta_data.get("type") == "不计收支":
            continue

        if status == DealStatus.SHOP_PENDING.value:
            continue

        orders.append(o)
        spec_order = pre_repay(o)
        if spec_order:
            orders.append(spec_order)

    google_order = pre_google()
    if google_order:
        orders.append(google_order)

    ir.orders = orders
    return ir


@lru_cache(maxsize=1)
def _get_accounts() -> dict:
    account_path = Path.home() / ".flow" / "account.json"
    if account_path.is_file():
        try:
            with open(account_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"解析配置文件失败 {account_path}: {e}")
    return {}


def pre_google():
    accounts = _get_accounts()
    google_obj = accounts.get("google_one")
    if not google_obj or (int(date.today().day) < int(google_obj.get("payday"))) or int(date.today().day) > 21:
        return None

    google_order = Order()
    google_order.pay_time = datetime.now()
    google_order.minus_account = google_obj.get("method_account")
    google_order.plus_account = google_obj.get("target_account")
    google_order.peer = google_obj.get("peer")
    google_order.item = google_obj.get("item")
    google_order.currency = google_obj.get("currency")
    google_order.money = Decimal(str(google_obj.get("money")))

    return google_order


def pre_repay(v: Order):
    if not v.note:
        return None
    keys = v.note.split(";")
    accounts = _get_accounts()
    account_obj = accounts.get(keys[0])
    if not account_obj or account_obj.get("type") != "repay":
        return None

    if "usd" in v.note.lower() and len(keys) >= 3:
        usd_money = keys[1]
        cny_money = keys[2]

        repay_order = Order()
        repay_order.pay_time = v.pay_time
        repay_order.plus_str = f"{usd_money} USD @@ {cny_money} CNY"
        repay_order.minus_str = f"-{cny_money} CNY"
        repay_order.minus_account = v.plus_account
        repay_order.plus_account = account_obj.get("target_account")
        repay_order.peer = account_obj.get("peer")
        repay_order.item = account_obj.get("item")

        return repay_order

    return None
