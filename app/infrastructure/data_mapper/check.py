__all__ = ["CheckDataMapper"]

from psycopg.rows import TupleRow

from app.application.ports import CheckGateway
from app.infrastructure.data_mapper.connection import get_cursor_context


class CheckDataMapper(CheckGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def check_db(self) -> bool:
        async with get_cursor_context(self._connection_string) as cur:
            await cur.execute("SELECT 1")
            row: TupleRow | None = await cur.fetchone()
            return row is not None and row[0] == 1
