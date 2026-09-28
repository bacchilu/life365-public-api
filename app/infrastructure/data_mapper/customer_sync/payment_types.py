"""Resolve preferred payment type codes in Life365."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import InvalidCustomerDataException

_SELECT_PAYMENT_TYPE = sql.SQL(
    "SELECT payment_type FROM public.payment_types WHERE payment_type = %s"
)


async def resolve_payment_type_code(
    cur: psycopg.AsyncCursor[TupleRow], code: str
) -> str:
    """Require an exact payment type key before storing it on a customer."""
    if not code or len(code) > 50:
        raise InvalidCustomerDataException(
            "Payment type code must contain 1 to 50 characters"
        )

    await cur.execute(_SELECT_PAYMENT_TYPE, (code,))
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(f"Unknown payment type code {code!r}")
    return row[0]
