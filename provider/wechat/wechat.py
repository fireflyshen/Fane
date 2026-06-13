from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from ir.ir import IR
from package.errors import ProviderError
from provider.wechat.converter import convert_to_ir
from provider.base import TabularProvider
from provider.wechat.wecaht_types import DealType, TxType, WechatOrder

REQUIRED_COLUMNS = (
    "交易时间",
    "交易单号",
    "商户单号",
    "收/支",
    "交易对方",
    "商品",
    "金额(元)",
    "当前状态",
    "支付方式",
    "交易类型",
)


class Wechat(TabularProvider[WechatOrder]):
    def iter_rows(self, filename: str) -> Iterable[Mapping[str, Any]]:
        start_index = self.find_header_index(filename)
        try:
            df = pd.read_excel(filename, skiprows=start_index, dtype=str)
            self.ensure_columns(df.columns, REQUIRED_COLUMNS, filename)
            for _, row in df.iterrows():
                yield row
        except ProviderError:
            raise
        except Exception as e:
            print(e)
            raise

    def find_header_index(self, filename: str) -> int:
        df_preview = pd.read_excel(filename, header=None, nrows=20)
        for i, row in df_preview.iterrows():
            if any("交易时间" in str(cell) for cell in row.values):
                return i
        return 0

    def translate_order(self, row: Mapping[str, Any]) -> None:
        pay_time = self.parse_datetime(row["交易时间"], "交易时间")

        wechat_order = WechatOrder(
            order_id=row["交易单号"],
            mechant_order_id=row["商户单号"],
            pay_time=pay_time,
            type=self.parse_enum(DealType, row["收/支"], "收/支"),
            type_original=row["收/支"],
            peer=row["交易对方"],
            item=row["商品"],
            money=str(row["金额(元)"]).replace("¥", ""),
            status=row["当前状态"],
            method=row["支付方式"],
            tx_type=self.parse_enum(TxType, row["交易类型"], "交易类型"),
            tx_type_original=row["交易类型"],
            commision="",
        )

        self.orders.append(wechat_order)

    def convert_orders(self, orders: list[WechatOrder]) -> IR:
        return convert_to_ir(orders)
