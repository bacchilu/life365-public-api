"""Offline tests for Life365 agent reference resolution."""

from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import IntegrationAgent
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.agents import resolve_agent_id


class _FakeCursor:
    def __init__(self, row: tuple[int] | None = None) -> None:
        self._row = row
        self.statements: list[tuple[str, tuple[int]]] = []

    async def execute(self, query: sql.SQL, params: tuple[int]) -> None:
        self.statements.append((query.as_string(), params))

    async def fetchone(self) -> tuple[int] | None:
        return self._row


def _agent(reference_id: int) -> IntegrationAgent:
    return IntegrationAgent(
        reference_id=reference_id,
        user_login="old-login",
        name="Old agent name",
        email="old@example.com",
        phone=None,
    )


@pytest.mark.anyio
async def test_null_agent_uses_fallback_without_a_lookup() -> None:
    cursor = _FakeCursor()

    result = await resolve_agent_id(cast(psycopg.AsyncCursor[TupleRow], cursor), None)

    assert result == 1
    assert cursor.statements == []


@pytest.mark.anyio
async def test_supplied_agent_uses_only_its_reference_id() -> None:
    cursor = _FakeCursor((117,))

    result = await resolve_agent_id(
        cast(psycopg.AsyncCursor[TupleRow], cursor), _agent(117)
    )

    assert result == 117
    assert len(cursor.statements) == 1
    statement, parameters = cursor.statements[0]
    assert statement == "SELECT id FROM public.agents WHERE id = %s"
    assert parameters == (117,)


@pytest.mark.anyio
async def test_unknown_agent_is_rejected() -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="Unknown agent"):
        await resolve_agent_id(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _agent(117)
        )

    assert cursor.statements[0][1] == (117,)


@pytest.mark.anyio
@pytest.mark.parametrize("reference_id", [0, -1])
async def test_non_positive_agent_reference_is_rejected(
    reference_id: int,
) -> None:
    cursor = _FakeCursor()

    with pytest.raises(InvalidCustomerDataException, match="must be positive"):
        await resolve_agent_id(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _agent(reference_id)
        )

    assert cursor.statements == []
