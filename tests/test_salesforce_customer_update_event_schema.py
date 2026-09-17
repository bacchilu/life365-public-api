from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.integrations.schemas.events import (
    CustomerUpdatedEventRequest,
    SalesforceEventRequest,
)

_EVENT_ADAPTER = TypeAdapter(SalesforceEventRequest)


def _update_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schemaVersion": 1,
        "eventId": "726c7c74-287d-44f2-b060-81fefa3d235d",
        "occurredAt": "2026-09-04T10:00:00Z",
        "eventType": "customer.updated",
        "resourceVersion": 2,
        "referenceId": 42,
        "data": {"company": {"name": "ACME Italia SRL"}},
    }
    event.update(overrides)
    return event


def test_update_event_requires_reference_and_data() -> None:
    for field_name in ("referenceId", "data"):
        event = _update_event()
        del event[field_name]

        with pytest.raises(ValidationError):
            CustomerUpdatedEventRequest.model_validate(event)


def test_update_event_rejects_create_event_type() -> None:
    with pytest.raises(ValidationError):
        _EVENT_ADAPTER.validate_python(
            _update_event(eventType="customer.created")
        )


def test_create_event_rejects_update_data_shape() -> None:
    event = _update_event(
        eventType="customer.created",
        resourceVersion=1,
        data={"company": {"name": "ACME Italia SRL"}},
    )
    del event["referenceId"]

    with pytest.raises(ValidationError):
        _EVENT_ADAPTER.validate_python(event)


def test_update_event_preserves_omitted_nested_properties() -> None:
    request = CustomerUpdatedEventRequest.model_validate(
        _update_event(
            data={
                "company": {
                    "website": None,
                    "primaryPhone": "",
                },
                "communicationPreferences": {
                    "newsletter": False,
                },
                "commercial": {
                    "paymentDays": 0,
                },
                "notes": {
                    "items": [],
                },
            }
        )
    )

    assert request.data.company.website is None
    assert request.data.company.primary_phone == ""
    assert request.data.company.name.__class__.__name__ == "UnsetType"
    assert request.data.communication_preferences.newsletter is False
    assert request.data.commercial.payment_days == 0
    assert request.data.notes.items == []
