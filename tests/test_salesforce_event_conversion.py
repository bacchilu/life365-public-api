import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.api.integrations.converters.events import convert_customer_event
from app.api.integrations.schemas.events import SalesforceEventRequest
from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
    IntegrationSalesChannelPatch,
)
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerUpdatedEvent,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
)
from app.application.dtos.customer_integration.unset import UNSET

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_EVENT_ADAPTER = TypeAdapter(SalesforceEventRequest)


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def test_complete_create_fixture_reaches_application_without_data_loss() -> None:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    request = _EVENT_ADAPTER.validate_python(payload)
    event = convert_customer_event(request)

    assert isinstance(event, CustomerCreatedEvent)
    assert event.schema_version == request.schema_version
    assert event.event_id == request.event_id
    assert event.occurred_at == request.occurred_at
    assert event.resource_version == request.resource_version
    assert _normalize(event.data) == _normalize(request.data.model_dump())


def test_nested_update_reaches_application_without_meaning_changes() -> None:
    request = _EVENT_ADAPTER.validate_python(
        {
            "schemaVersion": 1,
            "eventId": "726c7c74-287d-44f2-b060-81fefa3d235d",
            "occurredAt": "2026-09-22T10:00:00Z",
            "eventType": "customer.updated",
            "resourceVersion": 2,
            "referenceId": 42,
            "data": {
                "company": {"website": None, "primaryPhone": ""},
                "delivery": {"address": {"city": "Milan"}},
                "communicationPreferences": {"newsletter": False},
                "commercial": {
                    "preferredCategories": [],
                    "salesChannel": {"label": "Updated channel"},
                    "paymentDays": 0,
                    "creditGranted": "12.30",
                },
                "notes": {"items": []},
                "extensions": {
                    "extraData": {
                        "enabled": False,
                        "nested": {"removedValue": None},
                    }
                },
            },
        }
    )
    event = convert_customer_event(request)

    assert isinstance(event, CustomerUpdatedEvent)
    assert event.reference_id == 42
    assert event.data.credentials is UNSET

    assert isinstance(event.data.company, IntegrationCompanyPatch)
    assert event.data.company.name is UNSET
    assert event.data.company.website is None
    assert event.data.company.primary_phone == ""

    assert isinstance(event.data.delivery, IntegrationDeliveryPatch)
    assert isinstance(event.data.delivery.address, IntegrationAddressPatch)
    assert event.data.delivery.address.city == "Milan"
    assert event.data.delivery.address.street is UNSET

    assert isinstance(
        event.data.communication_preferences,
        IntegrationCommunicationPreferencesPatch,
    )
    assert event.data.communication_preferences.newsletter is False

    assert isinstance(event.data.commercial, IntegrationCommercialPatch)
    assert event.data.commercial.preferred_categories == ()
    assert isinstance(
        event.data.commercial.sales_channel,
        IntegrationSalesChannelPatch,
    )
    assert event.data.commercial.sales_channel.code is UNSET
    assert event.data.commercial.sales_channel.label == "Updated channel"
    assert event.data.commercial.payment_days == 0
    assert event.data.commercial.credit_granted == Decimal("12.30")

    assert isinstance(event.data.notes, IntegrationCustomerNotesPatch)
    assert event.data.notes.items == ()

    assert isinstance(event.data.extensions, IntegrationCustomerExtensionsPatch)
    assert event.data.extensions.parameters is UNSET
    assert event.data.extensions.extra_data == {
        "enabled": False,
        "nested": {"removedValue": None},
    }
