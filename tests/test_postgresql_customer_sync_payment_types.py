"""Offline tests for preferred payment type lookup."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.payment_types import (
    resolve_payment_type_code,
)


class _FakeCursor:
    def __init__(self, row: tuple[str] | None = None) -> None:
        self._row = row
        self.statements: list[tuple[str, tuple[str]]] = []

    async def execute(self, query: sql.SQL, params: tuple[str]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[str] | None:
        return self._row


@pytest.mark.anyio
async def test_existing_payment_type_uses_its_exact_key() -> None:
    cursor = _FakeCursor(("BONIFICO",))

    result = await resolve_payment_type_code(
        cast(psycopg.AsyncCursor[TupleRow], cursor), "BONIFICO"
    )

    assert result == "BONIFICO"
    assert cursor.statements == [
        (
            "SELECT payment_type FROM public.payment_types WHERE payment_type = %s",
            ("BONIFICO",),
        )
    ]


@pytest.mark.anyio
async def test_unknown_payment_type_is_rejected_without_normalizing() -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="Unknown payment type"):
        await resolve_payment_type_code(
            cast(psycopg.AsyncCursor[TupleRow], cursor), "bonifico"
        )

    assert cursor.statements[0][1] == ("bonifico",)


@pytest.mark.anyio
@pytest.mark.parametrize("code", ["", "x" * 51])
async def test_invalid_payment_type_length_is_rejected_before_query(
    code: str,
) -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="1 to 50 characters"):
        await resolve_payment_type_code(
            cast(psycopg.AsyncCursor[TupleRow], cursor), code
        )

    assert cursor.statements == []
