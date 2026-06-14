import logging
from collections.abc import Iterable, Mapping
from typing import Any, Optional, cast

import pandas as pd

from ir.ir import IR
from package.errors import ProviderError
from provider.ali.ali_types import AliOrder, DealStatus, DealType
from provider.ali.converter import convert_to_ir
from provider.base import TabularProvider

REQUIRED_COLUMNS = (
    "交易时间",
    "交易分类",
    "交易订单号",
    "商家订单号",
    "交易对方",
    "商品说明",
    "对方账号",
    "金额",
    "收/支",
    "交易状态",
    "收/付款方式",
    "备注",
)


class AliPay(TabularProvider[AliOrder]):
    def find_file_encodeing_and_index(self, filename: str) -> tuple[str, int]:
        encodings = ["utf-8", "gbk", "gb18030", "utf-8-sig"]
        lines: Optional[list[str]] = None
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
                return used_encoding, i
        raise ValueError(f"无法在文件中找到交易时间表头：{filename}")

    def iter_rows(self, filename: str) -> Iterable[Mapping[str, Any]]:
        encoding, index = self.find_file_encodeing_and_index(filename)
        try:
            df = pd.read_csv(
                filename,
                skiprows=index,
                header=0,
                encoding=encoding,
                dtype={"交易订单号": str, "商家订单号": str},
            )
            self.ensure_columns(df.columns, REQUIRED_COLUMNS, filename)
            for _, row in df.iterrows():
                yield cast(dict[str, Any], row.to_dict())
        except FileNotFoundError as fe:
            logging.error("文件未找到")
            raise
        except ProviderError:
            raise
        except Exception as e:
            logging.exception("发生未知错误")
            raise

    def parse_order(self, row: Mapping[str, Any]) -> AliOrder | None:
        pay_time = self.parse_datetime(row["交易时间"], "交易时间")

        # 如果首付款方式为空，说明这可能是已经被关闭的交易，不计入账本
        if pd.isna(row["收/付款方式"]):
            return None

        return AliOrder(
            category=row["交易分类"],
            deal_no=str(row["交易订单号"]).strip(),
            merchant_id=str(row["商家订单号"]).strip(),
            peer=row["交易对方"],
            item_name=row["商品说明"],
            peer_account=row["对方账号"],
            money=self.parse_decimal(row["金额"], "金额"),
            pay_time=pay_time,
            type=self.parse_enum(DealType, row["收/支"], "收/支"),
            status=self.parse_enum(DealStatus, row["交易状态"], "交易状态"),
            method=row["收/付款方式"],
            target_account="",
            method_account="",
            notes=str(row["备注"]),
            type_original=row["收/支"],
        )

    def convert_orders(self, orders: list[AliOrder]) -> IR:
        return convert_to_ir(orders)
