from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.integrations.schemas.events import (
    CustomerUpdatedEventRequest,
    SalesforceEventRequest,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import (
    CustomerUpdatedData,
)
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_service = CustomerSynchronizationService()


class SalesforceEventResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")


@router.post(
    "/integrations/salesforce/events",
    summary="Receive a Salesforce integration event",
    description=(
        "Temporary synchronization scaffold. It accepts a Salesforce customer "
        "event envelope and returns a mock acknowledgment without changing data."
    ),
    response_model=SalesforceEventResponse,
)
async def receive_salesforce_event(
    payload: SalesforceEventRequest,
) -> SalesforceEventResponse:
    if isinstance(payload, CustomerUpdatedEventRequest):
        event = CustomerUpdatedEvent(
            schema_version=cast(Literal[1], payload.schema_version),
            event_id=payload.event_id,
            occurred_at=payload.occurred_at,
            resource_version=payload.resource_version,
            reference_id=payload.reference_id,
            data=cast(CustomerUpdatedData, payload.data),
        )
    else:
        event = CustomerCreatedEvent(
            schema_version=cast(Literal[1], payload.schema_version),
            event_id=payload.event_id,
            occurred_at=payload.occurred_at,
            resource_version=payload.resource_version,
            data=cast(IntegrationCustomerData, payload.data),
        )

    result: CustomerSynchronizationResult = (
        await customer_synchronization_service.synchronize_customer(event)
    )
    return SalesforceEventResponse(
        success=result.success,
        eventId=payload.event_id,
        referenceId=result.reference_id,
    )
