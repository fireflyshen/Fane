from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

from ir.ir import IR
from package.errors import ProviderError

OrderT = TypeVar("OrderT")
EnumT = TypeVar("EnumT", bound=Enum)


class TabularProvider(ABC, Generic[OrderT]):
    def translate(self, filename: str) -> IR:
        self.validate_source(filename)
        orders: list[OrderT] = []
        for row in self.iter_rows(filename):
            order = self.parse_order(row)
            if order is not None:
                orders.append(order)
        return self.convert_orders(orders)

    def validate_source(self, filename: str) -> None:
        if not filename:
            raise ProviderError("请提供账单文件路径")
        if not Path(filename).is_file():
            raise ProviderError(f"账单文件不存在: {filename}")

    def ensure_columns(
        self, columns: Iterable[Any], required_columns: Iterable[str], filename: str
    ) -> None:
        available_columns = {str(column) for column in columns}
        missing_columns = [
            column for column in required_columns if column not in available_columns
        ]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ProviderError(f"账单文件缺少必要列: {missing} ({filename})")

    def parse_datetime(self, value: Any, field_name: str) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError as ve:
                raise ProviderError(
                    f"{field_name} 时间格式错误，应为 YYYY-MM-DD HH:MM:SS: {value}"
                ) from ve
        raise ProviderError(f"{field_name} 类型无法解析为时间: {value}")

    def parse_enum(self, enum_type: type[EnumT], value: Any, field_name: str) -> EnumT:
        try:
            return enum_type(value)
        except ValueError as ve:
            raise ProviderError(f"{field_name} 包含不支持的值: {value}") from ve

    def parse_decimal(self, value: Any, field_name: str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        normalized_value = str(value).replace("¥", "").replace(",", "").strip()
        try:
            return Decimal(normalized_value)
        except InvalidOperation as ve:
            raise ProviderError(f"{field_name} 金额格式错误: {value}") from ve

    @abstractmethod
    def iter_rows(self, filename: str) -> Iterable[Mapping[str, Any]]:
        pass

    @abstractmethod
    def parse_order(self, row: Mapping[str, Any]) -> Optional[OrderT]:
        pass

    @abstractmethod
    def convert_orders(self, orders: list[OrderT]) -> IR:
        pass
