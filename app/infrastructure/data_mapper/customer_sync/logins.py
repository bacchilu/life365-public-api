"""Validate and reserve a customer login within its insert transaction."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import (
    CustomerSynchronizationConflictException,
    InvalidCustomerDataException,
)

_LOCK_LOGIN = sql.SQL(
    "SELECT pg_advisory_xact_lock("
    "hashtextextended('customer-login:' || lower(btrim(%s)), 0))"
)
_FIND_LOGIN = sql.SQL(
    "SELECT id FROM public.customers "
    "WHERE lower(btrim(login)) = lower(%s) AND id <> COALESCE(%s, -1) LIMIT 1"
)


async def reserve_customer_login(
    cur: psycopg.AsyncCursor[TupleRow], login: str, *, current_id: int | None = None
) -> str:
    """Return the trimmed login if no other customer already uses it."""
    normalized = login.strip()
    if not normalized or len(normalized) > 50:
        raise InvalidCustomerDataException(
            "Customer login must contain 1 to 50 characters"
        )

    await cur.execute(_LOCK_LOGIN, (normalized,))
    await cur.fetchone()
    await cur.execute(_FIND_LOGIN, (normalized, current_id))
    if await cur.fetchone() is not None:
        raise CustomerSynchronizationConflictException("Customer login already exists")
    return normalized
