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
    return await resolve_region_name(cur, address.country_code, address.region_name)


async def resolve_region_name(
    cur: psycopg.AsyncCursor[TupleRow], country_code: str, region_name: str
) -> int:
    """Resolve a region after an address patch combines old and new fields."""
    await cur.execute(
        _SELECT_REGION_ID, (country_code, region_name)
    )
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(
            f"Unknown region {region_name!r} "
            f"for country {country_code!r}"
        )
    return row[0]
