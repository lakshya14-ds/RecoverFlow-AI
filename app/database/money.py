"""Exact monetary storage: decimal text on SQLite, NUMERIC on PostgreSQL."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator


class Money(TypeDecorator):
    impl = Numeric(20, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String(24) if dialect.name == "sqlite" else Numeric(20, 2))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or abs(amount) >= Decimal("1e18") or amount != amount.quantize(Decimal(".01")):
                raise ValueError("Money must be finite, within range and have at most two decimal places")
        except InvalidOperation as exc:
            raise ValueError("Invalid monetary amount") from exc
        return format(amount, ".2f") if dialect.name == "sqlite" else amount

    def process_result_value(self, value, dialect):
        return Decimal(str(value)).quantize(Decimal(".01")) if value is not None else None
