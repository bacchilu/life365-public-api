from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest

from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerSynchronizationResult,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

_EVENT_ID = UUID("726c7c74-287d-44f2-b060-81fefa3d235d")
_OCCURRED_AT = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


def _customer_data() -> IntegrationCustomerData:
    return cast(IntegrationCustomerData, "synthetic-customer-data")


def _event(*, occurred_at: datetime = _OCCURRED_AT) -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=_EVENT_ID,
        occurred_at=occurred_at,
        resource_version=1,
        data=_customer_data(),
    )


@pytest.mark.anyio
async def test_commit_saves_customer_event_and_version_together() -> None:
    store = InMemoryCustomerSynchronizationStore()
    event = _event()
    result = CustomerSynchronizationResult(success=True, reference_id=1)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        reference_id = await unit_of_work.customers.create_customer(event.data)
        await unit_of_work.resource_versions.save_resource_version(reference_id, 1)
        await unit_of_work.processed_events.save_processed_result(event, result)
        await unit_of_work.commit()

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        assert await unit_of_work.customers.customer_exists(1) is True
        assert await unit_of_work.resource_versions.get_resource_version(1) == 1
        assert await unit_of_work.processed_events.get_processed_result(event) == result


@pytest.mark.anyio
async def test_uncommitted_changes_are_not_visible() -> None:
    store = InMemoryCustomerSynchronizationStore()

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        await unit_of_work.customers.create_customer(_customer_data())

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        assert await unit_of_work.customers.customer_exists(1) is False


@pytest.mark.anyio
async def test_exception_rolls_back_all_changes() -> None:
    store = InMemoryCustomerSynchronizationStore()

    with pytest.raises(RuntimeError, match="stop transaction"):
        async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
            reference_id = await unit_of_work.customers.create_customer(
                _customer_data()
            )
            await unit_of_work.resource_versions.save_resource_version(reference_id, 1)
            raise RuntimeError("stop transaction")

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        assert await unit_of_work.customers.customer_exists(1) is False
        assert await unit_of_work.resource_versions.get_resource_version(1) is None


@pytest.mark.anyio
async def test_update_rejects_a_missing_customer() -> None:
    store = InMemoryCustomerSynchronizationStore()

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        with pytest.raises(CustomerNotFoundException):
            await unit_of_work.customers.update_customer(42, CustomerUpdatedData())


@pytest.mark.anyio
async def test_reused_event_id_with_different_content_is_a_conflict() -> None:
    store = InMemoryCustomerSynchronizationStore()
    event = _event()
    result = CustomerSynchronizationResult(success=True, reference_id=1)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        await unit_of_work.processed_events.save_processed_result(event, result)
        await unit_of_work.commit()

    conflicting_event = _event(occurred_at=_OCCURRED_AT + timedelta(seconds=1))
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as unit_of_work:
        with pytest.raises(CustomerSynchronizationConflictException):
            await unit_of_work.processed_events.get_processed_result(
                conflicting_event
            )
