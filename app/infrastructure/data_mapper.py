import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import Product
from app.application.ports import DataGateway

load_dotenv()
DATABASE_URL: str = os.environ["DATABASE_URL"]

PRODUCT_COLUMNS: tuple[str, ...] = (
    "id",
    "vendor_code",
    "isin",
    "titles",
    "descriptions",
    "brand_id",
    "owner_id",
    "level_1",
    "level_2",
    "level_3",
    "enabled",
    "featured",
    "qty_box",
    "weight_gr",
    "dim_length_mm",
    "dim_width_mm",
    "dim_height_mm",
    "color",
    "certificate",
    "type1",
    "type2",
    "barcodes",
    "extra_specs",
    "keywords",
    "excluded_countries",
    "creation_date",
    "last_update",
)

PRODUCT_SELECT_QUERY = sql.SQL(
    "SELECT {columns} FROM {table} ORDER BY {id_column} LIMIT %s OFFSET %s"
).format(
    columns=sql.SQL(", ").join(sql.Identifier(column) for column in PRODUCT_COLUMNS),
    table=sql.Identifier("public", "products"),
    id_column=sql.Identifier("id"),
)


@asynccontextmanager
async def get_cursor_context(
    connection_string: str,
) -> AsyncIterator[psycopg.AsyncCursor[TupleRow]]:
    async with await psycopg.AsyncConnection.connect(connection_string) as conn:
        async with conn.cursor() as cur:
            yield cur


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _int_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, int))


def _product_from_row(row: TupleRow) -> Product:
    return Product(
        id=row[0],
        vendor_code=row[1],
        isin=row[2],
        titles=_str_dict(row[3]),
        descriptions=_str_dict(row[4]),
        brand_id=row[5],
        owner_id=row[6],
        level_1=row[7],
        level_2=row[8],
        level_3=row[9],
        enabled=row[10] if row[10] is not None else False,
        featured=row[11] if row[11] is not None else False,
        qty_box=row[12] if row[12] is not None else 1,
        weight_gr=row[13] if row[13] is not None else 0,
        dim_length_mm=row[14],
        dim_width_mm=row[15],
        dim_height_mm=row[16],
        color=row[17],
        certificate=row[18],
        type1=row[19],
        type2=row[20],
        barcodes=_str_tuple(row[21]),
        extra_specs=_dict(row[22]),
        keywords=_dict(row[23]),
        excluded_countries=_int_tuple(row[24]),
        creation_date=row[25],
        last_update=row[26] if row[26] is not None else 0,
    )


class DataMapper(DataGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def check_db(self) -> bool:
        async with get_cursor_context(self._connection_string) as cur:
            await cur.execute("SELECT 1")
            row: TupleRow | None = await cur.fetchone()
            return row is not None and row[0] == 1

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        async with get_cursor_context(self._connection_string) as cur:
            await cur.execute(PRODUCT_SELECT_QUERY, (limit, offset))
            rows: list[TupleRow] = await cur.fetchall()

        return [_product_from_row(row) for row in rows]
