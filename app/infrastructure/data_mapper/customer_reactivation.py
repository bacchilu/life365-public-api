"""Check one customer's inactivity without changing local data."""

import psycopg
from psycopg.rows import scalar_row

from app.application.exceptions import DBException
from app.application.ports import CustomerReactivationReader

# Match the inactive-customer job in life365-portal-api.
_QUERY = """
    SELECT COALESCE((
        SELECT MAX(o.order_date) < CURRENT_TIMESTAMP - INTERVAL '90 days'
        FROM public.orders AS o
        WHERE o.customer_id = c.id
          AND o.logistic_state IN ('CONFIRMED', 'DELIVERED', 'UNDELIVERABLE')
    ), FALSE)
    FROM public.customers AS c
    WHERE c.id = %s
"""


class PostgreSQLCustomerReactivationDataMapper(CustomerReactivationReader):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def is_inactive(self, customer_id: int) -> bool | None:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor(row_factory=scalar_row) as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(_QUERY, (customer_id,))
                return await cursor.fetchone()
        except psycopg.Error:
            raise DBException("Customer reactivation lookup failed") from None
