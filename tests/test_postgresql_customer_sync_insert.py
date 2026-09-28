"""Offline tests for inserting a synchronized customer row."""

from collections.abc import Mapping
from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import DBException
from app.infrastructure.data_mapper.customer_sync.insert import insert_customer_row


class _FakeCursor:
    def __init__(self, row: tuple[int] | None = (42,)) -> None:
        self._row = row
        self.statements: list[tuple[str, dict[str, object]]] = []

    async def execute(
        self, query: sql.Composable, params: Mapping[str, object]
    ) -> None:
        self.statements.append((query.as_string(), dict(params)))

    async def fetchone(self) -> tuple[int] | None:
        return self._row


@pytest.mark.anyio
async def test_insert_uses_named_values_and_returns_generated_id() -> None:
    cursor = _FakeCursor()
    values = {"login": "acme", "pass": "customer-password", "notes_open": 0}

    result = await insert_customer_row(
        cast(psycopg.AsyncCursor[TupleRow], cursor), values
    )

    assert result == 42
    assert len(cursor.statements) == 1
    query, params = cursor.statements[0]
    assert query == (
        'INSERT INTO public.customers ("login", "pass", "notes_open") '
        'VALUES (%(login)s, %(pass)s, %(notes_open)s) RETURNING id'
    )
    assert params == values
    assert "customer-password" not in query


@pytest.mark.anyio
@pytest.mark.parametrize("values", [{}, {"id": 42, "login": "acme"}])
async def test_insert_rejects_missing_values_or_supplied_id(
    values: dict[str, object],
) -> None:
    cursor = _FakeCursor()

    with pytest.raises(ValueError):
        await insert_customer_row(cast(psycopg.AsyncCursor[TupleRow], cursor), values)

    assert cursor.statements == []


@pytest.mark.anyio
async def test_insert_rejects_a_missing_returned_id() -> None:
    cursor = _FakeCursor(row=None)

    with pytest.raises(DBException, match="returned no ID"):
        await insert_customer_row(
            cast(psycopg.AsyncCursor[TupleRow], cursor), {"login": "acme"}
        )

    assert len(cursor.statements) == 1


@pytest.mark.anyio
async def test_invalid_parameter_name_is_rejected_before_execution() -> None:
    cursor = _FakeCursor()

    with pytest.raises(ValueError, match="invalid name"):
        await insert_customer_row(
            cast(psycopg.AsyncCursor[TupleRow], cursor),
            {"login); DROP TABLE customers;--": "acme"},
        )

    assert cursor.statements == []
