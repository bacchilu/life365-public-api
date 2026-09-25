"""Create a stable event fingerprint without storing customer credentials."""

import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.dtos.customer_integration.events import CustomerIntegrationEvent
from app.application.dtos.customer_integration.unset import UNSET

_FINGERPRINT_DOMAIN = b"customer-synchronization-event:v1\0"


def _number(value: int | float | Decimal) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Event numbers must be finite")
        value = Decimal(str(value))
    elif isinstance(value, int):
        value = Decimal(value)

    if not value.is_finite():
        raise ValueError("Event numbers must be finite")
    return "0" if value.is_zero() else str(value.normalize())


def _canonical_value(value: Any) -> object:
    if value is UNSET:
        raise TypeError("UNSET must be omitted from the event fingerprint")
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, (int, float, Decimal)):
        return ["number", _number(value)]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Event dates must include a UTC offset")
        return ["datetime", value.astimezone(UTC).isoformat()]
    if is_dataclass(value) and not isinstance(value, type):
        properties = [
            [item.name, _canonical_value(member)]
            for item in fields(value)
            if (member := getattr(value, item.name)) is not UNSET
        ]
        return [
            "dataclass",
            f"{type(value).__module__}.{type(value).__qualname__}",
            properties,
        ]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Event object keys must be strings")
        return [
            "object",
            [[key, _canonical_value(value[key])] for key in sorted(value)],
        ]
    if isinstance(value, tuple):
        return ["tuple", [_canonical_value(item) for item in value]]
    if isinstance(value, list):
        return ["list", [_canonical_value(item) for item in value]]
    raise TypeError(f"Unsupported event value type: {type(value).__name__}")


def event_fingerprint(event: CustomerIntegrationEvent, secret: bytes) -> bytes:
    """Return a 32-byte HMAC; keep the secret stable across process restarts."""
    if len(secret) < 32:
        raise ValueError("Event fingerprint secret must be at least 32 bytes")

    payload = json.dumps(
        _canonical_value(event),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hmac.digest(secret, _FINGERPRINT_DOMAIN + payload, hashlib.sha256)
