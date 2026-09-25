"""Offline tests for PostgreSQL customer resource versions."""

from collections.abc import Iterable
from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import CustomerSynchronizationConflictException
from app.infrastructure.data_mapper.customer_sync.versions import (
    PostgreSQLCustomerResourceVersionDataMapper,
)


class _FakeCursor:
    def __init__(self, rows: Iterable[tuple[int] | None]) -> None:
        self._rows = iter(rows)
        self.statements: list[tuple[str, tuple[int, ...]]] = []

    async def execute(self, query: sql.SQL, params: tuple[int, ...]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[int] | None:
        return next(self._rows)


def _mapper(
    rows: Iterable[tuple[int] | None],
) -> tuple[PostgreSQLCustomerResourceVersionDataMapper, _FakeCursor]:
    cursor = _FakeCursor(rows)
    mapper = PostgreSQLCustomerResourceVersionDataMapper(
        cast(psycopg.AsyncCursor[TupleRow], cursor)
    )
    return mapper, cursor


@pytest.mark.anyio
async def test_get_version_locks_and_returns_the_current_value() -> None:
    mapper, cursor = _mapper([(3,)])

    assert await mapper.get_resource_version(42) == 3
    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert parameters == (42,)
    assert "FOR UPDATE" in statement


@pytest.mark.anyio
async def test_get_version_returns_none_when_no_row_exists() -> None:
    mapper, cursor = _mapper([None])

    assert await mapper.get_resource_version(42) is None
    assert len(cursor.statements) == 1


@pytest.mark.anyio
async def test_save_version_uses_a_conditional_upsert() -> None:
    mapper, cursor = _mapper([(4,)])

    await mapper.save_resource_version(42, 4)

    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert parameters == (42, 4)
    assert "ON CONFLICT (customer_id) DO UPDATE" in statement
    assert "stored.resource_version = EXCLUDED.resource_version - 1" in statement


@pytest.mark.anyio
async def test_save_version_rejects_a_conflicting_value() -> None:
    mapper, cursor = _mapper([None])

    with pytest.raises(
        CustomerSynchronizationConflictException,
        match="Customer 42 version changed",
    ):
        await mapper.save_resource_version(42, 4)

    assert len(cursor.statements) == 1
