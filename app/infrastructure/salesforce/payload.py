"""Serialize the shared application contract, not API request models."""

import math
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TypeAlias
from uuid import UUID

from app.application.dtos.customer_integration.export import CustomerExportEvent
from app.application.exceptions import InvalidCustomerDataException

from .normalization import normalize_customer_data

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


def _camel_case(name: str) -> str:
    first, *parts = name.split("_")
    return first + "".join(part.capitalize() for part in parts)


def _value(value: object) -> JsonValue:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _camel_case(item.name): _value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Decimal):
        try:
            valid = value.is_finite() and value == value.quantize(Decimal("0.01"))
        except InvalidOperation:
            valid = False
        if not valid:
            raise InvalidCustomerDataException(
                "Customer export financial values must have at most two decimal places"
            )
        return format(value, ".2f")
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise InvalidCustomerDataException(
                "Customer export timestamps need a UTC offset"
            )
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidCustomerDataException(
                    "Customer export JSON keys must be strings"
                )
            result[key] = _value(item)
        return result
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidCustomerDataException(
            "Customer export contains a non-finite number"
        )
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise InvalidCustomerDataException("Customer export contains an unsupported value")


def customer_event_payload(event: CustomerExportEvent) -> dict[str, JsonValue]:
    payload = _value(replace(event, data=normalize_customer_data(event.data)))
    assert isinstance(payload, dict)
    return payload
