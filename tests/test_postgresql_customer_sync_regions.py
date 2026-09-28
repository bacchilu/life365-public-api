"""Offline tests for Life365 region reference resolution."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.address import IntegrationAddress
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.regions import resolve_region_id


class _FakeCursor:
    def __init__(self, row: tuple[int] | None) -> None:
        self._row = row
        self.statements: list[tuple[str, tuple[str, str]]] = []

    async def execute(self, query: sql.SQL, params: tuple[str, str]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[int] | None:
        return self._row


def _address(region_name: str = "Forlì-Cesena") -> IntegrationAddress:
    return IntegrationAddress(
        street="Via Roma 10",
        city="Forlì",
        postal_code="47121",
        country_code="IT",
        region_name=region_name,
    )


@pytest.mark.anyio
async def test_resolve_region_uses_country_and_exact_enabled_name() -> None:
    cursor = _FakeCursor((117,))

    result = await resolve_region_id(
        cast(psycopg.AsyncCursor[TupleRow], cursor), _address()
    )

    assert result == 117
    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert parameters == ("IT", "Forlì-Cesena")
    assert "upper(c.iso_alpha_2) = %s" in statement
    assert "r.region_name = %s" in statement
    assert "r.enabled = true" in statement


@pytest.mark.anyio
async def test_resolve_region_rejects_an_unknown_pair() -> None:
    cursor = _FakeCursor(None)

    with pytest.raises(InvalidCustomerDataException, match="Unknown region"):
        await resolve_region_id(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _address("Not a region")
        )

    assert cursor.statements[0][1] == ("IT", "Not a region")
