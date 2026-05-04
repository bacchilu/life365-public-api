__all__ = ["DATABASE_URL", "DataMapper"]

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.rows import TupleRow

from app.application.domain import Product
from app.application.ports import DataGateway
from app.infrastructure.data_mapper.products import get_products as execute_get_products

load_dotenv()
DATABASE_URL: str = os.environ["DATABASE_URL"]


@asynccontextmanager
async def get_cursor_context(
    connection_string: str,
) -> AsyncIterator[psycopg.AsyncCursor[TupleRow]]:
    async with await psycopg.AsyncConnection.connect(connection_string) as conn:
        async with conn.cursor() as cur:
            yield cur


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
            return await execute_get_products(cur, limit=limit, offset=offset)
