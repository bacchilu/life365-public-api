"""Offline tests for shop-group reference resolution."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.operations import IntegrationShopGroup
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.shop_groups import (
    resolve_shop_group_ids,
)


class _FakeCursor:
    def __init__(self, rows: list[tuple[int]]) -> None:
        self._rows = rows
        self.statements: list[tuple[str, tuple[list[int]]]] = []

    async def execute(self, query: sql.SQL, params: tuple[list[int]]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchall(self) -> list[tuple[int]]:
        return self._rows


def _group(code: str, label: str = "Old label") -> IntegrationShopGroup:
    return IntegrationShopGroup(code=code, label=label)


@pytest.mark.anyio
async def test_empty_groups_need_no_database_query() -> None:
    cursor = _FakeCursor([])

    result = await resolve_shop_group_ids(
        cast(psycopg.AsyncCursor[TupleRow], cursor), ()
    )

    assert result == []
    assert cursor.statements == []


@pytest.mark.anyio
async def test_group_codes_keep_input_order_and_ignore_labels() -> None:
    cursor = _FakeCursor([(1,), (2,), (3,), (36,)])
    groups = (
        _group("closed-activity"),
        _group("professional-group"),
        _group("rei-la-rete"),
        _group("geser-prodigix"),
    )

    result = await resolve_shop_group_ids(
        cast(psycopg.AsyncCursor[TupleRow], cursor), groups
    )

    assert result == [36, 3, 1, 2]
    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert statement == "SELECT id FROM public.shop_groups WHERE id = ANY(%s)"
    assert parameters == ([36, 3, 1, 2],)


@pytest.mark.anyio
async def test_unknown_group_code_is_rejected_before_query() -> None:
    cursor = _FakeCursor([])

    with pytest.raises(InvalidCustomerDataException, match="Unknown shop-group"):
        await resolve_shop_group_ids(
            cast(psycopg.AsyncCursor[TupleRow], cursor),
            (_group("unknown", "Professional Group"),),
        )

    assert cursor.statements == []


@pytest.mark.anyio
async def test_mapped_group_missing_from_database_is_rejected() -> None:
    cursor = _FakeCursor([(3,)])
    groups = (_group("professional-group"), _group("closed-activity"))

    with pytest.raises(InvalidCustomerDataException, match="closed-activity"):
        await resolve_shop_group_ids(
            cast(psycopg.AsyncCursor[TupleRow], cursor), groups
        )

    assert cursor.statements[0][1] == ([3, 36],)
