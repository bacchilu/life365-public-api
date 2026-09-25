"""PostgreSQL storage for completed customer synchronization events."""

import hashlib
import hmac
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
)
from app.application.exceptions import CustomerSynchronizationConflictException
from app.application.ports import ProcessedCustomerEventGateway

from .fingerprint import event_fingerprint

_LOCK_EVENT = sql.SQL("SELECT pg_advisory_xact_lock(%s)")
_SELECT_EVENT = sql.SQL(
    """
    SELECT event_fingerprint, result_success, result_reference_id
    FROM public.customer_synchronization_events
    WHERE event_id = %s
    """
)
_INSERT_EVENT = sql.SQL(
    """
    INSERT INTO public.customer_synchronization_events (
        event_id,
        event_fingerprint,
        schema_version,
        event_type,
        occurred_at,
        resource_version,
        result_success,
        result_reference_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
    """
)


def _lock_key(event_id: UUID) -> int:
    return int.from_bytes(
        hashlib.sha256(event_id.bytes).digest()[:8], "big", signed=True
    )


class PostgreSQLProcessedCustomerEventDataMapper(ProcessedCustomerEventGateway):
    def __init__(
        self, cur: psycopg.AsyncCursor[TupleRow], fingerprint_secret: bytes
    ) -> None:
        if len(fingerprint_secret) < 32:
            raise ValueError("Event fingerprint secret must be at least 32 bytes")
        self._cur = cur
        self._fingerprint_secret = fingerprint_secret

    async def _lock_event(self, event_id: UUID) -> None:
        await self._cur.execute(_LOCK_EVENT, (_lock_key(event_id),))
        await self._cur.fetchone()

    async def _stored_result(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult | None:
        await self._cur.execute(_SELECT_EVENT, (event.event_id,))
        row = await self._cur.fetchone()
        if row is None:
            return None

        stored_fingerprint, success, reference_id = row
        expected_fingerprint = event_fingerprint(event, self._fingerprint_secret)
        if not hmac.compare_digest(bytes(stored_fingerprint), expected_fingerprint):
            raise CustomerSynchronizationConflictException(
                f"Event id {event.event_id} has different content"
            )
        return CustomerSynchronizationResult(
            success=success, reference_id=reference_id
        )

    async def get_processed_result(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult | None:
        await self._lock_event(event.event_id)
        return await self._stored_result(event)

    async def save_processed_result(
        self,
        event: CustomerIntegrationEvent,
        result: CustomerSynchronizationResult,
    ) -> None:
        await self._lock_event(event.event_id)
        stored = await self._stored_result(event)
        if stored is not None:
            if stored != result:
                raise CustomerSynchronizationConflictException(
                    f"Event id {event.event_id} has a different result"
                )
            return

        await self._cur.execute(
            _INSERT_EVENT,
            (
                event.event_id,
                event_fingerprint(event, self._fingerprint_secret),
                event.schema_version,
                event.event_type,
                event.occurred_at,
                event.resource_version,
                result.success,
                result.reference_id,
            ),
        )
        if await self._cur.fetchone() is None:
            stored = await self._stored_result(event)
            if stored != result:
                raise CustomerSynchronizationConflictException(
                    f"Event id {event.event_id} has a different result"
                )
