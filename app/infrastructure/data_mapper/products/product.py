import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import Product

from .utils import PRODUCT_COLUMNS, product_from_row

QUERY = sql.SQL("SELECT {columns} FROM {table} WHERE id = %s").format(
    columns=sql.SQL(", ").join(sql.Identifier(column) for column in PRODUCT_COLUMNS),
    table=sql.Identifier("public", "products"),
)


async def get_product(
    cur: psycopg.AsyncCursor[TupleRow], product_id: int
) -> Product | None:
    await cur.execute(QUERY, (product_id,))
    data: TupleRow | None = await cur.fetchone()
    return product_from_row(data) if data is not None else None
