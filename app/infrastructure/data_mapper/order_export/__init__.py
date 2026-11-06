"""Read a full order in one consistent, explicitly read-only transaction."""

import psycopg
from psycopg.rows import dict_row

from app.application.dtos.order_integration import IntegrationOrderData
from app.application.exceptions import DBException
from app.application.ports import OrderExportReader

from .order import order_from_rows
from .query import DETAILS_QUERY, ORDER_EXISTS_QUERY, ORDER_QUERY, SHIPPING_QUERY


class PostgreSQLOrderExportDataMapper(OrderExportReader):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_order(self, reference_id: int) -> IntegrationOrderData | None:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                await cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                parameters = {"reference_id": reference_id}
                await cursor.execute(ORDER_QUERY, parameters)
                row = await cursor.fetchone()
                if row is None:
                    return None
                await cursor.execute(DETAILS_QUERY, parameters)
                details = await cursor.fetchall()
                shipping: list[dict[str, object]] = []
                if row["delivery_cost"] != 0:
                    await cursor.execute(SHIPPING_QUERY)
                    shipping = await cursor.fetchall()
                return order_from_rows(row, details, shipping)
        except psycopg.Error:
            raise DBException("Order export lookup failed") from None

    async def order_exists(self, reference_id: int) -> bool:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor() as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(ORDER_EXISTS_QUERY, {"reference_id": reference_id})
                row = await cursor.fetchone()
                return row is not None and row[0] is True
        except psycopg.Error:
            raise DBException("Order existence lookup failed") from None
