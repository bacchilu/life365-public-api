__all__ = ["DATABASE_URL", "get_cursor_context"]

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.rows import TupleRow

load_dotenv()
DATABASE_URL: str = os.environ["DATABASE_URL"]


@asynccontextmanager
async def get_cursor_context(
    connection_string: str,
) -> AsyncIterator[psycopg.AsyncCursor[TupleRow]]:
    async with await psycopg.AsyncConnection.connect(connection_string) as conn:
        async with conn.cursor() as cur:
            yield cur
