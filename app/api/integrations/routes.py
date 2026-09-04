from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.application.services.customer_synchronization_service import (
    CustomerEventType,
    CustomerSynchronizationResult,
    CustomerSynchronizationService,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_service = CustomerSynchronizationService()


class IntegrationCustomerCredentials(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=1, repr=False)


class IntegrationCustomerData(BaseModel):
    credentials: IntegrationCustomerCredentials


class CustomerUpdatedData(BaseModel):
    pass


class SalesforceEventRequest(BaseModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    event_id: UUID = Field(alias="eventId")
    occurred_at: datetime = Field(alias="occurredAt")
    event_type: CustomerEventType = Field(alias="eventType")
    reference_id: int | None = Field(default=None, alias="referenceId", gt=0)
    data: IntegrationCustomerData | CustomerUpdatedData | None = None


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
    data = payload.data.model_dump() if payload.data is not None else None
    result: CustomerSynchronizationResult = (
        await customer_synchronization_service.synchronize_customer(
            schema_version=payload.schema_version,
            event_id=payload.event_id,
            occurred_at=payload.occurred_at,
            event_type=payload.event_type,
            reference_id=payload.reference_id,
            data=data,
        )
    )
    return SalesforceEventResponse(
        success=result.success,
        eventId=payload.event_id,
        referenceId=result.reference_id,
    )
