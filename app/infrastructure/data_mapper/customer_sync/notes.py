"""Convert integration customer notes to the legacy PostgreSQL fields."""

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerNote,
)
from app.application.exceptions import InvalidCustomerDataException


def _legacy_note_date(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCustomerDataException("notes.items[].occurredAt needs a UTC offset")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def notes_jsonb(items: tuple[IntegrationCustomerNote, ...]) -> Jsonb:
    """Keep the legacy date, note, and open keys for every item."""
    return Jsonb(
        [
            {
                "date": _legacy_note_date(item.occurred_at),
                "note": item.text,
                "open": item.open,
            }
            for item in items
        ]
    )


def open_notes_count(items: tuple[IntegrationCustomerNote, ...]) -> int:
    """Derive notes_open from the same items stored in _notes."""
    return sum(1 for item in items if item.open)
