from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

CustomerEventType = Literal[
    "customer.created",
    "customer.updated",
    "customer.deleted",
]


@dataclass(frozen=True, slots=True)
class CustomerSynchronizationResult:
    success: bool
    reference_id: int


class CustomerSynchronizationService:
    async def synchronize_customer(
        self,
        *,
        schema_version: int,
        event_id: UUID,
        occurred_at: datetime,
        event_type: CustomerEventType,
        reference_id: int | None,
        data: Mapping[str, object] | None,
    ) -> CustomerSynchronizationResult:
        return CustomerSynchronizationResult(
            success=True, reference_id=reference_id if reference_id is not None else 42
        )
