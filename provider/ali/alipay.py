import logging
from datetime import datetime

import pandas as pd

from ir.ir import IR
from provider.ali.ali_types import DealType, DealStatus, AliOrder
from provider.ali.converter import convert_to_ir


class AliPay:
    orders: list[AliOrder]

    def __init__(self):
        self.orders = []

    def find_file_encodeing_and_index(self, filename: str) -> tuple:
        global start_index
        self.orders = []
        encodings = ["utf-8", "gbk", "gb18030", "utf-8-sig"]
        lines = None
        used_encoding = "utf-8"

        for enc in encodings:
            try:
                with open(filename, "r", encoding=enc) as f:
                    lines = f.readlines()
                used_encoding = enc
                break
            except UnicodeDecodeError:
                continue
        if lines is None:
            logging.error("无法识别文件编码格式")
            raise ValueError(f"无法使用 {encodings} 解码文件：{filename}")
        for i, line in enumerate(lines):
            if "交易时间" in line:
                start_index = i
                break
        return used_encoding, start_index

    def parse_ir(self, filename: str, start_index, encoding):
        try:
            df = pd.read_csv(
                filename,
                skiprows=start_index,
                header=0,
                encoding=encoding,
                dtype={"交易订单号": str, "商家订单号": str},
            )

            for row in df.to_dict("records"):
                self.translate_order(row)

            ir = convert_to_ir(self.orders)
            return ir
        except FileNotFoundError as fe:
            logging.error("文件未找到")
            raise
        except Exception as e:
            logging.exception("发生未知错误")
            raise

    def translate_order(self, row: dict):
        pay_time_raw = row["交易时间"]
        if isinstance(pay_time_raw, str):
            pay_time = datetime.strptime(pay_time_raw.strip(), "%Y-%m-%d %H:%M:%S")
        else:
            pay_time = pay_time_raw

        # 如果首付款方式为空，说明这可能是已经被关闭的交易，不计入账本
        if pd.isna(row["收/付款方式"]):
            return

        ali_order = AliOrder(
            category=row["交易分类"],
            deal_no=str(row["交易订单号"]).strip(),
            merchant_id=str(row["商家订单号"]).strip(),
            peer=row["交易对方"],
            item_name=row["商品说明"],
            peer_account=row["对方账号"],
            money=row["金额"],
            pay_time=pay_time,
            type=DealType(row["收/支"]),
            status=DealStatus(row["交易状态"]),
            method=row["收/付款方式"],
            target_account="",
            method_account="",
            notes=str(row["备注"]),
            type_original=row["收/支"],
        )

        self.orders.append(ali_order)

    def translate(self, filename: str) -> IR:
        encoding, index = self.find_file_encodeing_and_index(filename)
        return self.parse_ir(filename=filename, start_index=index, encoding=encoding)
