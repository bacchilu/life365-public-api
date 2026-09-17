"""Salesforce customer event request schemas."""

from datetime import datetime
from re import fullmatch
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.customer import IntegrationCustomerData
from app.api.integrations.schemas.customer_patch import CustomerUpdatedData


class _CustomerEventRequestBase(IntegrationRequestModel):
    schema_version: StrictInt = Field(alias="schemaVersion", ge=1, le=1)
    event_id: UUID = Field(alias="eventId")
    occurred_at: AwareDatetime = Field(alias="occurredAt")
    resource_version: StrictInt = Field(alias="resourceVersion", gt=0)

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


class CustomerCreatedEventRequest(_CustomerEventRequestBase):
    resource_version: StrictInt = Field(alias="resourceVersion", ge=1, le=1)
    event_type: Literal["customer.created"] = Field(alias="eventType")
    data: IntegrationCustomerData


class CustomerUpdatedEventRequest(_CustomerEventRequestBase):
    resource_version: StrictInt = Field(alias="resourceVersion", gt=1)
    event_type: Literal["customer.updated"] = Field(alias="eventType")
    reference_id: StrictInt = Field(alias="referenceId", gt=0)
    data: CustomerUpdatedData


SalesforceEventRequest: TypeAlias = Annotated[
    CustomerCreatedEventRequest | CustomerUpdatedEventRequest,
    Field(discriminator="event_type"),
]
