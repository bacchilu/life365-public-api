"""Offline tests for preferred category reference resolution."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import IntegrationCategory
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.categories import (
    resolve_category_ids,
)


class _FakeCursor:
    def __init__(self, rows: list[tuple[int]]) -> None:
        self._rows = rows
        self.statements: list[tuple[str, tuple[list[int]]]] = []

    async def execute(self, query: sql.SQL, params: tuple[list[int]]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchall(self) -> list[tuple[int]]:
        return self._rows


def _category(code: str, label: str = "Old label") -> IntegrationCategory:
    return IntegrationCategory(code=code, label=label)


@pytest.mark.anyio
async def test_empty_categories_need_no_database_query() -> None:
    cursor = _FakeCursor([])

    result = await resolve_category_ids(
        cast(psycopg.AsyncCursor[TupleRow], cursor), ()
    )

    assert result == []
    assert cursor.statements == []


@pytest.mark.anyio
async def test_category_codes_keep_input_order_and_ignore_labels() -> None:
    cursor = _FakeCursor([(1,), (14,)])
    categories = (_category("networking"), _category("cartridge-toner"))

    result = await resolve_category_ids(
        cast(psycopg.AsyncCursor[TupleRow], cursor), categories
    )

    assert result == [14, 1]
    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert statement == "SELECT id FROM public.categories WHERE id = ANY(%s)"
    assert parameters == ([14, 1],)


@pytest.mark.anyio
async def test_unknown_category_code_is_rejected_before_query() -> None:
    cursor = _FakeCursor([])

    with pytest.raises(InvalidCustomerDataException, match="Unknown category"):
        await resolve_category_ids(
            cast(psycopg.AsyncCursor[TupleRow], cursor),
            (_category("unknown", "Cartridge&Toner"),),
        )

    assert cursor.statements == []


@pytest.mark.anyio
async def test_mapped_category_missing_from_database_is_rejected() -> None:
    cursor = _FakeCursor([(1,)])
    categories = (_category("cartridge-toner"), _category("networking"))

    with pytest.raises(InvalidCustomerDataException, match="networking"):
        await resolve_category_ids(
            cast(psycopg.AsyncCursor[TupleRow], cursor), categories
        )

    assert cursor.statements[0][1] == ([1, 14],)
