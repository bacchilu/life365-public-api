"""Offline tests for the PostgreSQL processed-event mapper."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCustomerCredentialsPatch,
)
from app.application.exceptions import CustomerSynchronizationConflictException
from app.infrastructure.data_mapper.customer_sync.events import (
    PostgreSQLProcessedCustomerEventDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.fingerprint import event_fingerprint

_KEY = b"test-customer-sync-hmac-key-32-bytes"
_EVENT_ID = UUID(int=1)
_RESULT = CustomerSynchronizationResult(success=True, reference_id=42)
_PASSWORD = "synthetic-password"


class _FakeCursor:
    def __init__(self, rows: Iterable[tuple[object, ...] | None]) -> None:
        self._rows = iter(rows)
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    async def execute(
        self, query: sql.SQL, params: tuple[object, ...]
    ) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[object, ...] | None:
        return next(self._rows)


def _event() -> CustomerUpdatedEvent:
    return CustomerUpdatedEvent(
        schema_version=1,
        event_id=_EVENT_ID,
        occurred_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
        resource_version=2,
        reference_id=42,
        data=CustomerUpdatedData(
            credentials=IntegrationCustomerCredentialsPatch(password=_PASSWORD)
        ),
    )


def _mapper(
    rows: Iterable[tuple[object, ...] | None],
) -> tuple[PostgreSQLProcessedCustomerEventDataMapper, _FakeCursor]:
    cursor = _FakeCursor(rows)
    mapper = PostgreSQLProcessedCustomerEventDataMapper(
        cast(psycopg.AsyncCursor[TupleRow], cursor), _KEY
    )
    return mapper, cursor


@pytest.mark.anyio
async def test_save_records_a_fingerprint_and_original_result() -> None:
    event = _event()
    mapper, cursor = _mapper([(None,), None, (_EVENT_ID,)])

    await mapper.save_processed_result(event, _RESULT)

    assert len(cursor.statements) == 3
    assert "pg_advisory_xact_lock" in cursor.statements[0][0]
    assert "SELECT event_fingerprint" in cursor.statements[1][0]
    statement, parameters = cursor.statements[2]
    assert "ON CONFLICT (event_id) DO NOTHING" in statement
    assert parameters[0] == _EVENT_ID
    assert parameters[1] == event_fingerprint(event, _KEY)
    assert parameters[-2:] == (True, 42)
    assert _PASSWORD not in repr(cursor.statements)


@pytest.mark.anyio
async def test_replay_returns_the_stored_result() -> None:
    event = _event()
    fingerprint = event_fingerprint(event, _KEY)
    mapper, cursor = _mapper([(None,), (memoryview(fingerprint), True, 42)])

    result = await mapper.get_processed_result(event)

    assert result == _RESULT
    assert len(cursor.statements) == 2


@pytest.mark.anyio
async def test_reusing_an_event_id_with_changed_content_fails() -> None:
    original = _event()
    changed = replace(original, resource_version=3)
    mapper, cursor = _mapper(
        [(None,), (event_fingerprint(original, _KEY), True, 42)]
    )

    with pytest.raises(CustomerSynchronizationConflictException):
        await mapper.get_processed_result(changed)

    assert len(cursor.statements) == 2


@pytest.mark.anyio
async def test_insert_conflict_checks_the_stored_result() -> None:
    event = _event()
    fingerprint = event_fingerprint(event, _KEY)
    mapper, cursor = _mapper(
        [(None,), None, None, (fingerprint, True, 42)]
    )

    await mapper.save_processed_result(event, _RESULT)

    assert len(cursor.statements) == 4


@pytest.mark.anyio
async def test_insert_conflict_rejects_a_different_result() -> None:
    event = _event()
    fingerprint = event_fingerprint(event, _KEY)
    mapper, cursor = _mapper(
        [(None,), None, None, (fingerprint, True, 99)]
    )

    with pytest.raises(CustomerSynchronizationConflictException):
        await mapper.save_processed_result(event, _RESULT)

    assert len(cursor.statements) == 4
