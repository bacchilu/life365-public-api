from datetime import datetime
from re import fullmatch
from uuid import UUID

from fastapi import APIRouter
from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.events import (
    CustomerEventType,
    CustomerSynchronizationResult,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_service = CustomerSynchronizationService()


class CustomerUpdatedData(IntegrationRequestModel):
    pass


class SalesforceEventRequest(IntegrationRequestModel):
    schema_version: StrictInt = Field(alias="schemaVersion", ge=1, le=1)
    event_id: UUID = Field(alias="eventId")
    occurred_at: AwareDatetime = Field(alias="occurredAt")
    resource_version: StrictInt = Field(alias="resourceVersion", gt=0)
    event_type: CustomerEventType = Field(alias="eventType")
    reference_id: StrictInt | None = Field(default=None, alias="referenceId", gt=0)
    data: IntegrationCustomerData | CustomerUpdatedData

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_timestamp_format(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            return value
        raise ValueError("Date-time must be an RFC 3339 string with a UTC offset")

    @model_validator(mode="after")
    def validate_event_shape(self) -> "SalesforceEventRequest":
        if self.event_type == "customer.created":
            if self.reference_id is not None:
                raise ValueError("customer.created must not contain referenceId")
            if self.resource_version != 1:
                raise ValueError("customer.created must use resourceVersion 1")
            if not isinstance(self.data, IntegrationCustomerData):
                raise ValueError("customer.created requires complete customer data")
        elif self.reference_id is None:
            raise ValueError("customer.updated requires referenceId")
        return self


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
