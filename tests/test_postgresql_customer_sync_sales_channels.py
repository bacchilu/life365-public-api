"""Offline tests for sales-channel reference resolution."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import (
    IntegrationSalesChannel,
)
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.sales_channels import (
    resolve_sales_channel_id,
)


class _FakeCursor:
    def __init__(self, row: tuple[int] | None = None) -> None:
        self._row = row
        self.statements: list[tuple[str, tuple[int]]] = []

    async def execute(self, query: sql.SQL, params: tuple[int]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[int] | None:
        return self._row


def _channel(code: str) -> IntegrationSalesChannel:
    return IntegrationSalesChannel(code=code, label="Old label")


@pytest.mark.anyio
@pytest.mark.parametrize("channel_id", [*range(1, 16), *range(18, 23)])
async def test_known_code_maps_to_an_existing_id(channel_id: int) -> None:
    cursor = _FakeCursor((channel_id,))

    result = await resolve_sales_channel_id(
        cast(psycopg.AsyncCursor[TupleRow], cursor), _channel(f"N{channel_id}")
    )

    assert result == channel_id
    assert cursor.statements == [
        ("SELECT id FROM public.sales_channels WHERE id = %s", (channel_id,))
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("code", ["N16", "N17", "N23", "n13"])
async def test_unknown_code_is_rejected_before_query(code: str) -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="Unknown sales-channel"):
        await resolve_sales_channel_id(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _channel(code)
        )

    assert cursor.statements == []


@pytest.mark.anyio
async def test_mapped_channel_missing_from_database_is_rejected() -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="Unavailable sales-channel"):
        await resolve_sales_channel_id(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _channel("N13")
        )

    assert cursor.statements[0][1] == (13,)
