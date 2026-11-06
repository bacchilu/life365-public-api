"""Validate database values without repairing or truncating historical data."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.application.exceptions import InvalidOrderDataException


def identifier(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidOrderDataException(f"Order {field} must be a positive integer")
    return value


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidOrderDataException(f"Order {field} must contain text")
    return value


def money(value: object, field: str) -> Decimal:
    if not isinstance(value, (Decimal, int, str)) or isinstance(value, bool):
        raise InvalidOrderDataException(
            f"Order {field} must be an exact decimal amount"
        )
    try:
        result = Decimal(value)
        if not result.is_finite() or result != result.quantize(Decimal("0.01")):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise InvalidOrderDataException(
            f"Order {field} must be a finite cent amount"
        ) from None
    return result


def timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidOrderDataException("Order date must be a timestamp")
    # Historical Life365 readers interpret timestamp-without-zone values as UTC.
    return (
        value.replace(tzinfo=UTC)
        if value.utcoffset() is None
        else value.astimezone(UTC)
    )
