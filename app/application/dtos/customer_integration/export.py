"""Outbound events describe an existing Life365 customer in both operations."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from .customer import IntegrationCustomerData
from .events import CustomerEventType


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerExportEvent:
    event_id: UUID
    occurred_at: datetime
    event_type: CustomerEventType
    reference_id: int
    data: IntegrationCustomerData = field(repr=False)
    schema_version: Literal[1] = field(default=1, init=False)


@dataclass(frozen=True, slots=True)
class CustomerExportResult:
    success: bool
    event_id: UUID
    reference_id: int
    account_id: str
