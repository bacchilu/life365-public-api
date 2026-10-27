"""Resolve integration sales-channel codes to Life365 IDs."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import (
    IntegrationSalesChannel,
)
from app.application.exceptions import InvalidCustomerDataException

from .reference_codes import SALES_CHANNEL_IDS_BY_CODE as _SALES_CHANNEL_IDS_BY_CODE

_SELECT_SALES_CHANNEL_ID = sql.SQL("SELECT id FROM public.sales_channels WHERE id = %s")


async def resolve_sales_channel_id(
    cur: psycopg.AsyncCursor[TupleRow], channel: IntegrationSalesChannel
) -> int:
    """Verify a mapped channel ID without using its descriptive label."""
    return await resolve_sales_channel_code(cur, channel.code)


async def resolve_sales_channel_code(
    cur: psycopg.AsyncCursor[TupleRow], code: str
) -> int:
    """Resolve a code supplied in a partial sales-channel patch."""
    channel_id = _SALES_CHANNEL_IDS_BY_CODE.get(code)
    if channel_id is None:
        raise InvalidCustomerDataException(f"Unknown sales-channel code {code!r}")

    await cur.execute(_SELECT_SALES_CHANNEL_ID, (channel_id,))
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(f"Unavailable sales-channel code {code!r}")
    return row[0]
