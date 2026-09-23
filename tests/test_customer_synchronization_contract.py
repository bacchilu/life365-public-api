import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from uuid import UUID

import pytest

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequestData,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
    CustomerSynchronizationException,
    CustomerVersionGapException,
    InvalidCustomerReferenceException,
    StaleCustomerVersionException,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

_EVENT_ID = UUID("726c7c74-287d-44f2-b060-81fefa3d235d")
_OCCURRED_AT = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


def _created_event() -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=_EVENT_ID,
        occurred_at=_OCCURRED_AT,
        resource_version=1,
        data=_customer_data(),
    )


def _updated_event() -> CustomerUpdatedEvent:
    return CustomerUpdatedEvent(
        schema_version=1,
        event_id=_EVENT_ID,
        occurred_at=_OCCURRED_AT,
        resource_version=2,
        reference_id=42,
        data=CustomerUpdatedData(),
    )


def _service() -> CustomerSynchronizationService:
    store = InMemoryCustomerSynchronizationStore()
    unit_of_work = InMemoryCustomerSynchronizationUnitOfWork(store)
    return CustomerSynchronizationService(unit_of_work)


def test_created_event_has_full_data_and_no_customer_reference() -> None:
    event = _created_event()

    assert event.event_type == "customer.created"
    assert event.resource_version == 1
    assert "reference_id" not in {event_field.name for event_field in fields(event)}


def test_updated_event_requires_reference_and_patch_data() -> None:
    event = _updated_event()

    assert event.event_type == "customer.updated"
    assert event.reference_id == 42
    assert isinstance(event.data, CustomerUpdatedData)


def test_events_are_frozen_and_slotted() -> None:
    event = _created_event()

    assert not hasattr(event, "__dict__")
    with pytest.raises(FrozenInstanceError):
        event.resource_version = 2  # type: ignore[misc]


def test_synchronization_result_contains_success_and_life365_id() -> None:
    result = CustomerSynchronizationResult(success=True, reference_id=42)

    assert result.success is True
    assert result.reference_id == 42


@pytest.mark.parametrize(
    "error_type",
    [
        CustomerNotFoundException,
        InvalidCustomerReferenceException,
        StaleCustomerVersionException,
        CustomerVersionGapException,
        CustomerSynchronizationConflictException,
    ],
)
def test_specific_errors_share_the_synchronization_base(
    error_type: type[CustomerSynchronizationException],
) -> None:
    assert issubclass(error_type, CustomerSynchronizationException)


def test_service_accepts_one_typed_event() -> None:
    parameters = tuple(
        signature(CustomerSynchronizationService.synchronize_customer).parameters
    )

    assert parameters == ("self", "event")


def test_service_requires_one_unit_of_work() -> None:
    parameters = tuple(signature(CustomerSynchronizationService).parameters)

    assert parameters == ("unit_of_work",)


@pytest.mark.anyio
async def test_service_returns_the_result_for_each_event_type() -> None:
    service = _service()

    created = await service.synchronize_customer(_created_event())
    updated = await service.synchronize_customer(
        replace(
            _updated_event(),
            event_id=UUID("726c7c74-287d-44f2-b060-81fefa3d235e"),
            reference_id=created.reference_id,
        )
    )

    assert created == CustomerSynchronizationResult(success=True, reference_id=1)
    assert updated == CustomerSynchronizationResult(success=True, reference_id=1)
