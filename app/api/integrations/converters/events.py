"""Convert validated API events to application events."""

from typing import Literal, cast

from app.api.integrations.converters.customer import (
    convert_customer_data,
    convert_customer_patch,
)
from app.api.integrations.schemas.events import (
    CustomerCreatedEventRequest,
    CustomerUpdatedEventRequest,
    SalesforceEventRequest,
)
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerIntegrationEvent,
    CustomerUpdatedEvent,
)


def convert_customer_event(
    source: SalesforceEventRequest,
) -> CustomerIntegrationEvent:
    schema_version = cast(Literal[1], source.schema_version)

    if isinstance(source, CustomerUpdatedEventRequest):
        return CustomerUpdatedEvent(
            schema_version=schema_version,
            event_id=source.event_id,
            occurred_at=source.occurred_at,
            resource_version=source.resource_version,
            reference_id=source.reference_id,
            data=convert_customer_patch(source.data),
        )

    if isinstance(source, CustomerCreatedEventRequest):
        return CustomerCreatedEvent(
            schema_version=schema_version,
            event_id=source.event_id,
            occurred_at=source.occurred_at,
            resource_version=source.resource_version,
            data=convert_customer_data(source.data),
        )

    raise TypeError(f"Unsupported customer event request: {type(source).__name__}")
