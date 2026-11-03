"""Read-only product export; stock identifiers and local data are not changed."""

import psycopg
from psycopg.rows import dict_row

from app.application.dtos.product_integration import IntegrationProductData
from app.application.exceptions import DBException
from app.application.ports import ProductExportReader

from .product import product_from_row
from .query import PRODUCT_EXISTS_QUERY, PRODUCT_QUERY


class PostgreSQLProductExportDataMapper(ProductExportReader):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_product(self, reference_id: int) -> IntegrationProductData | None:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(PRODUCT_QUERY, {"reference_id": reference_id})
                row = await cursor.fetchone()
                return product_from_row(row) if row is not None else None
        except psycopg.Error:
            raise DBException("Product export lookup failed") from None

    async def product_exists(self, reference_id: int) -> bool:
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._connection_string
                ) as connection,
                connection.cursor() as cursor,
            ):
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(
                    PRODUCT_EXISTS_QUERY, {"reference_id": reference_id}
                )
                row = await cursor.fetchone()
                return row is not None and row[0] is True
        except psycopg.Error:
            raise DBException("Product existence lookup failed") from None
