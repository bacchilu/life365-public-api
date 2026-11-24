"""Read only the order fields needed for post-order cross-selling."""

import psycopg

from app.application.dtos.order_cross_sell import OrderCrossSellState
from app.application.exceptions import DBException
from app.application.ports import OrderCrossSellReader

_QUERY = """
    SELECT customer_id, logistic_state, invoice_doc_n
    FROM public.orders
    WHERE id = %s
"""


class PostgreSQLOrderCrossSellDataMapper(OrderCrossSellReader):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_cross_sell_state(self, order_id: int) -> OrderCrossSellState | None:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor() as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(_QUERY, (order_id,))
                row = await cursor.fetchone()
                return OrderCrossSellState(*row) if row is not None else None
        except psycopg.Error:
            raise DBException("Order cross-sell lookup failed") from None
