"""Read-only customer export adapter; no synchronization event tables are used."""

import psycopg
from psycopg.rows import dict_row

from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.exceptions import DBException
from app.application.ports import CustomerExportReader

from .customer import customer_from_row
from .query import CUSTOMER_QUERY


class PostgreSQLCustomerExportDataMapper(CustomerExportReader):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_customer(self, reference_id: int) -> IntegrationCustomerData | None:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(CUSTOMER_QUERY, (reference_id,))
                row = await cursor.fetchone()
                return customer_from_row(row) if row is not None else None
        except psycopg.Error:
            raise DBException("Customer export lookup failed") from None
