import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import Product

from .utils import PRODUCT_COLUMNS, product_from_row

QUERY = sql.SQL(
    "SELECT {columns} FROM {table} ORDER BY {id_column} LIMIT %s OFFSET %s"
).format(
    columns=sql.SQL(", ").join(sql.Identifier(column) for column in PRODUCT_COLUMNS),
    table=sql.Identifier("public", "products"),
    id_column=sql.Identifier("id"),
)


async def get_products(
    cur: psycopg.AsyncCursor[TupleRow], limit: int, offset: int
) -> list[Product]:
    await cur.execute(QUERY, (limit, offset))
    rows: list[TupleRow] = await cur.fetchall()
    return [product_from_row(row) for row in rows]
