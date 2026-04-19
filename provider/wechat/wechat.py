import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ir.ir import IR
from provider.wechat.wecaht_types import WechatOrder, DealType, TxType
from provider.wechat.converter import convert_to_ir


class Wechat:
    orders: list[WechatOrder]

    def __init__(self):
        self.orders = []

    def translate(self, filename: str) -> IR:
        self.orders = []
        start_index = 0
        df_preview = pd.read_excel(filename, header=None, nrows=20)
        for i, row in df_preview.iterrows():
            if any("交易时间" in str(cell) for cell in row.values):
                start_index = i
                break
        try:
            df = pd.read_excel(
                filename,
                skiprows=start_index,
            )
            for row in df.to_dict("records"):
                self.translate_order(row)

            ir = convert_to_ir(self.orders)

            return ir
        except Exception as e:
            print(e)
            raise

    def translate_order(self, row: dict):
        from datetime import datetime

        pay_time_raw = row["交易时间"]
        if isinstance(pay_time_raw, str):
            pay_time = datetime.strptime(pay_time_raw.strip(), "%Y-%m-%d %H:%M:%S")
        else:
            pay_time = pay_time_raw  # pandas 可能已解析为 datetime

        wechat_order = WechatOrder(
            order_id=row["交易单号"],
            mechant_order_id=row["商户单号"],
            pay_time=pay_time,
            type=DealType(row["收/支"]),
            type_original=row["收/支"],
            peer=row["交易对方"],
            item=row["商品"],
            money=str(row["金额(元)"]).replace("¥", ""),
            status=row["当前状态"],
            method=row["支付方式"],
            tx_type=TxType(row["交易类型"]),
            tx_type_original=row["交易类型"],
            commision="",
        )

        self.orders.append(wechat_order)
