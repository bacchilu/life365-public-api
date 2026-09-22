from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.integrations.converters.events import convert_customer_event
from app.api.integrations.schemas.events import SalesforceEventRequest
from app.application.dtos.customer_integration.events import (
    CustomerSynchronizationResult,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_store = InMemoryCustomerSynchronizationStore()


def get_customer_synchronization_service() -> CustomerSynchronizationService:
    unit_of_work = InMemoryCustomerSynchronizationUnitOfWork(
        customer_synchronization_store
    )
    return CustomerSynchronizationService(unit_of_work)


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
    customer_synchronization_service: Annotated[
        CustomerSynchronizationService,
        Depends(get_customer_synchronization_service),
    ],
) -> SalesforceEventResponse:
    event = convert_customer_event(payload)
    result: CustomerSynchronizationResult = (
        await customer_synchronization_service.synchronize_customer(event)
    )
    return SalesforceEventResponse(
        success=result.success,
        eventId=payload.event_id,
        referenceId=result.reference_id,
    )
