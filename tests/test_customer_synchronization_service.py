import json
from dataclasses import replace
from datetime import UTC, datetime
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
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
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

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_OCCURRED_AT = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


@pytest.fixture
def customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


@pytest.fixture
def sync_context() -> tuple[
    CustomerSynchronizationService,
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
]:
    store = InMemoryCustomerSynchronizationStore()
    work = InMemoryCustomerSynchronizationUnitOfWork(store)
    return CustomerSynchronizationService(work), store, work


def _create(
    data: IntegrationCustomerData,
    *,
    event_number: int = 1,
    version: int = 1,
) -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=UUID(int=event_number),
        occurred_at=_OCCURRED_AT,
        resource_version=version,
        data=data,
    )


def _update(
    reference_id: int,
    *,
    event_number: int = 2,
    version: int = 2,
    patch: CustomerUpdatedData | None = None,
) -> CustomerUpdatedEvent:
    return CustomerUpdatedEvent(
        schema_version=1,
        event_id=UUID(int=event_number),
        occurred_at=_OCCURRED_AT,
        resource_version=version,
        reference_id=reference_id,
        data=patch if patch is not None else CustomerUpdatedData(),
    )


@pytest.mark.anyio
async def test_create_stores_the_full_customer_and_generated_id(
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    first_event = _create(customer_data)

    first = await service.synchronize_customer(first_event)
    second = await service.synchronize_customer(_create(customer_data, event_number=2))

    assert first == CustomerSynchronizationResult(success=True, reference_id=1)
    assert second == CustomerSynchronizationResult(success=True, reference_id=2)
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) == customer_data
        assert await work.customers.get_customer(2) == customer_data
        assert await work.resource_versions.get_resource_version(1) == 1
        assert await work.processed_events.get_processed_result(first_event) == first


@pytest.mark.anyio
async def test_update_applies_a_nested_patch_and_saves_its_result(
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    created = await service.synchronize_customer(_create(customer_data))
    event = _update(
        created.reference_id,
        patch=CustomerUpdatedData(
            company=IntegrationCompanyPatch(website=None, primary_phone=""),
            communication_preferences=IntegrationCommunicationPreferencesPatch(
                newsletter=False
            ),
        ),
    )

    updated = await service.synchronize_customer(event)

    assert updated == created
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(created.reference_id)
        assert customer is not None
        assert customer.company.name == customer_data.company.name
        assert customer.company.website is None
        assert customer.company.primary_phone == ""
        assert customer.communication_preferences.newsletter is False
        assert await work.resource_versions.get_resource_version(1) == 2
        assert await work.processed_events.get_processed_result(event) == updated


@pytest.mark.anyio
async def test_replay_returns_the_original_result_without_another_change(
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    created_event = _create(customer_data)
    created = await service.synchronize_customer(created_event)
    updated_event = _update(
        created.reference_id,
        patch=CustomerUpdatedData(company=IntegrationCompanyPatch(name="New name")),
    )
    updated = await service.synchronize_customer(updated_event)

    assert await service.synchronize_customer(created_event) == created
    assert await service.synchronize_customer(updated_event) == updated
    assert await service.synchronize_customer(
        _create(customer_data, event_number=3)
    ) == CustomerSynchronizationResult(success=True, reference_id=2)
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(1)
        assert customer is not None
        assert customer.company.name == "New name"
        assert await work.resource_versions.get_resource_version(1) == 2


@pytest.mark.anyio
async def test_same_event_id_with_different_content_is_a_conflict(
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    original = _create(customer_data)
    await service.synchronize_customer(original)
    changed_data = replace(
        customer_data,
        company=replace(customer_data.company, name="Other name"),
    )

    with pytest.raises(CustomerSynchronizationConflictException):
        await service.synchronize_customer(replace(original, data=changed_data))

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) == customer_data
        assert await work.resource_versions.get_resource_version(1) == 1
        assert await work.processed_events.get_processed_result(original) is not None


@pytest.mark.anyio
async def test_update_of_a_missing_customer_does_not_save_the_event(
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    event = _update(42)

    with pytest.raises(CustomerNotFoundException):
        await service.synchronize_customer(event)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(42) is None
        assert await work.resource_versions.get_resource_version(42) is None
        assert await work.processed_events.get_processed_result(event) is None


@pytest.mark.anyio
async def test_update_rejects_a_nonpositive_reference(
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, _, _ = sync_context

    with pytest.raises(InvalidCustomerReferenceException):
        await service.synchronize_customer(_update(0))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("version", "error_type"),
    [
        (1, StaleCustomerVersionException),
        (3, CustomerVersionGapException),
    ],
)
async def test_update_rejects_stale_and_skipped_versions(
    version: int,
    error_type: type[Exception],
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    await service.synchronize_customer(_create(customer_data))
    event = _update(1, version=version)

    with pytest.raises(error_type):
        await service.synchronize_customer(event)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) == customer_data
        assert await work.resource_versions.get_resource_version(1) == 1
        assert await work.processed_events.get_processed_result(event) is None


@pytest.mark.anyio
async def test_create_rejects_a_version_other_than_one(
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, _ = sync_context
    event = _create(customer_data, version=2)

    with pytest.raises(CustomerSynchronizationConflictException):
        await service.synchronize_customer(event)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None
        assert await work.processed_events.get_processed_result(event) is None


@pytest.mark.anyio
async def test_commit_failure_returns_no_success_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    customer_data: IntegrationCustomerData,
    sync_context: tuple[
        CustomerSynchronizationService,
        InMemoryCustomerSynchronizationStore,
        InMemoryCustomerSynchronizationUnitOfWork,
    ],
) -> None:
    service, store, unit_of_work = sync_context
    event = _create(customer_data)

    async def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(unit_of_work, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await service.synchronize_customer(event)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None
        assert await work.resource_versions.get_resource_version(1) is None
        assert await work.processed_events.get_processed_result(event) is None
