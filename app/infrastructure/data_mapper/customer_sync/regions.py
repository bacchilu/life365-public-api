"""Resolve integration addresses to Life365 region IDs."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.address import IntegrationAddress
from app.application.exceptions import InvalidCustomerDataException

_SELECT_REGION_ID = sql.SQL(
    """
    SELECT r.id
    FROM public.regions AS r
    JOIN public.countries AS c ON c.id = r.country_id
    WHERE upper(c.iso_alpha_2) = %s
      AND r.region_name = %s
      AND r.enabled = true
    """
)


async def resolve_region_id(
    cur: psycopg.AsyncCursor[TupleRow], address: IntegrationAddress
) -> int:
    """Find one enabled region using the contract's exact region name."""
    await cur.execute(
        _SELECT_REGION_ID, (address.country_code, address.region_name)
    )
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(
            f"Unknown region {address.region_name!r} "
            f"for country {address.country_code!r}"
        )
    return row[0]
