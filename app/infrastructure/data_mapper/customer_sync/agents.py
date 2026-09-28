"""Resolve the assigned Life365 agent for customer synchronization."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import IntegrationAgent
from app.application.exceptions import InvalidCustomerDataException

_FALLBACK_AGENT_ID = 1
_SELECT_AGENT_ID = sql.SQL("SELECT id FROM public.agents WHERE id = %s")


async def resolve_agent_id(
    cur: psycopg.AsyncCursor[TupleRow], agent: IntegrationAgent | None
) -> int:
    """Use the Life365 fallback or verify the supplied agent reference."""
    if agent is None:
        return _FALLBACK_AGENT_ID

    if agent.reference_id <= 0:
        raise InvalidCustomerDataException("Agent reference must be positive")

    await cur.execute(_SELECT_AGENT_ID, (agent.reference_id,))
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(
            f"Unknown agent reference {agent.reference_id}"
        )
    return row[0]
