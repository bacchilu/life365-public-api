"""Resolve integration sales-channel codes to Life365 IDs."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import (
    IntegrationSalesChannel,
)
from app.application.exceptions import InvalidCustomerDataException

_SALES_CHANNEL_IDS_BY_CODE: dict[str, int] = {
    "N1": 1,
    "N2": 2,
    "N3": 3,
    "N4": 4,
    "N5": 5,
    "N6": 6,
    "N7": 7,
    "N8": 8,
    "N9": 9,
    "N10": 10,
    "N11": 11,
    "N12": 12,
    "N13": 13,
    "N14": 14,
    "N15": 15,
    "N18": 18,
    "N19": 19,
    "N20": 20,
    "N21": 21,
    "N22": 22,
}

_SELECT_SALES_CHANNEL_ID = sql.SQL(
    "SELECT id FROM public.sales_channels WHERE id = %s"
)


async def resolve_sales_channel_id(
    cur: psycopg.AsyncCursor[TupleRow], channel: IntegrationSalesChannel
) -> int:
    """Verify a mapped channel ID without using its descriptive label."""
    channel_id = _SALES_CHANNEL_IDS_BY_CODE.get(channel.code)
    if channel_id is None:
        raise InvalidCustomerDataException(
            f"Unknown sales-channel code {channel.code!r}"
        )

    await cur.execute(_SELECT_SALES_CHANNEL_ID, (channel_id,))
    row = await cur.fetchone()
    if row is None:
        raise InvalidCustomerDataException(
            f"Unavailable sales-channel code {channel.code!r}"
        )
    return row[0]
