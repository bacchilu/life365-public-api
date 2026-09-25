"""PostgreSQL resource versions for customer synchronization."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.exceptions import CustomerSynchronizationConflictException
from app.application.ports import CustomerResourceVersionGateway

_GET_VERSION = sql.SQL(
    """
    SELECT resource_version
    FROM public.customer_synchronization_versions
    WHERE customer_id = %s
    FOR UPDATE
    """
)
_SAVE_VERSION = sql.SQL(
    """
    INSERT INTO public.customer_synchronization_versions AS stored (
        customer_id, resource_version
    ) VALUES (%s, %s)
    ON CONFLICT (customer_id) DO UPDATE
    SET resource_version = EXCLUDED.resource_version,
        updated_at = now()
    WHERE stored.resource_version = EXCLUDED.resource_version - 1
    RETURNING resource_version
    """
)


class PostgreSQLCustomerResourceVersionDataMapper(CustomerResourceVersionGateway):
    def __init__(self, cur: psycopg.AsyncCursor[TupleRow]) -> None:
        self._cur = cur

    async def get_resource_version(self, reference_id: int) -> int | None:
        await self._cur.execute(_GET_VERSION, (reference_id,))
        row = await self._cur.fetchone()
        return row[0] if row is not None else None

    async def save_resource_version(
        self, reference_id: int, resource_version: int
    ) -> None:
        await self._cur.execute(_SAVE_VERSION, (reference_id, resource_version))
        if await self._cur.fetchone() is None:
            raise CustomerSynchronizationConflictException(
                f"Customer {reference_id} version changed during synchronization"
            )
