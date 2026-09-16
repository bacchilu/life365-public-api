"""Typed events for Salesforce customer synchronization."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias
from uuid import UUID

from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData

CustomerEventType: TypeAlias = Literal["customer.created", "customer.updated"]


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerCreatedEvent:
    schema_version: Literal[1]
    event_id: UUID
    occurred_at: datetime
    resource_version: int
    data: IntegrationCustomerData
    event_type: Literal["customer.created"] = field(
        default="customer.created", init=False
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerUpdatedEvent:
    schema_version: Literal[1]
    event_id: UUID
    occurred_at: datetime
    resource_version: int
    reference_id: int
    data: CustomerUpdatedData
    event_type: Literal["customer.updated"] = field(
        default="customer.updated", init=False
    )


CustomerIntegrationEvent: TypeAlias = CustomerCreatedEvent | CustomerUpdatedEvent


@dataclass(frozen=True, slots=True)
class CustomerSynchronizationResult:
    success: bool
    reference_id: int
