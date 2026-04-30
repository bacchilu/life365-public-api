import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.rows import TupleRow

from app.application.ports import DataGateway

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
