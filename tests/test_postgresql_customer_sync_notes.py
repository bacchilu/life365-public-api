"""Offline tests for customer note conversion."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerNote,
)
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.notes import (
    notes_jsonb,
    open_notes_count,
)


def test_empty_notes_remain_an_empty_json_array_with_zero_open_count() -> None:
    value = notes_jsonb(())

    assert isinstance(value, Jsonb)
    assert value.obj == []
    assert open_notes_count(()) == 0


def test_notes_use_legacy_keys_and_utc_date_format() -> None:
    items = (
        IntegrationCustomerNote(
            occurred_at=datetime(
                2026,
                9,
                25,
                12,
                30,
                1,
                227000,
                tzinfo=timezone(timedelta(hours=2)),
            ),
            text="First note",
            open=True,
        ),
        IntegrationCustomerNote(
            occurred_at=datetime(2026, 9, 25, 11, 0, tzinfo=UTC),
            text="Closed note",
            open=False,
        ),
    )

    value = notes_jsonb(items)

    assert value.obj == [
        {
            "date": "2026-09-25T10:30:01.227000+00:00",
            "note": "First note",
            "open": True,
        },
        {
            "date": "2026-09-25T11:00:00.000000+00:00",
            "note": "Closed note",
            "open": False,
        },
    ]
    assert open_notes_count(items) == 1


def test_note_without_utc_offset_is_rejected() -> None:
    items = (
        IntegrationCustomerNote(
            occurred_at=datetime(2026, 9, 25, 10, 30),
            text="Invalid date",
            open=False,
        ),
    )

    with pytest.raises(InvalidCustomerDataException, match="UTC offset"):
        notes_jsonb(items)
