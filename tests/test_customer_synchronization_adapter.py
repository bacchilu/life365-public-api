import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequestData,
)
from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
    IntegrationSalesChannelPatch,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerSynchronizationResult,
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
from app.application.exceptions import CustomerSynchronizationConflictException
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


@pytest.fixture
def customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


@pytest.mark.anyio
async def test_create_and_update_store_complete_customer(
    customer_data: IntegrationCustomerData,
) -> None:
    store = InMemoryCustomerSynchronizationStore()
    data = replace(
        customer_data,
        extensions=replace(
            customer_data.extensions,
            extra_data={"keep": {"value": 1, "remove": 2}, "items": [1, 2]},
        ),
    )

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        reference_id = await work.customers.create_customer(data)
        assert reference_id == 1
        assert await work.customers.get_customer(reference_id) == data
        await work.commit()

    patch = CustomerUpdatedData(
        company=IntegrationCompanyPatch(website=None, primary_phone=""),
        delivery=IntegrationDeliveryPatch(
            address=IntegrationAddressPatch(city="Milano")
        ),
        communication_preferences=IntegrationCommunicationPreferencesPatch(
            newsletter=False
        ),
        commercial=IntegrationCommercialPatch(
            preferred_categories=(),
            sales_channel=IntegrationSalesChannelPatch(label="Updated channel"),
            payment_days=0,
            credit_granted=Decimal("12.30"),
        ),
        notes=IntegrationCustomerNotesPatch(items=()),
        extensions=IntegrationCustomerExtensionsPatch(
            extra_data={
                "keep": {"remove": None, "added": False},
                "items": [],
            }
        ),
    )

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        await work.customers.update_customer(reference_id, patch)
        await work.commit()

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(reference_id)

    assert customer is not None
    assert customer.company.name == data.company.name
    assert customer.company.website is None
    assert customer.company.primary_phone == ""
    assert customer.delivery.address is not None
    assert data.delivery.address is not None
    assert customer.delivery.address.city == "Milano"
    assert customer.delivery.address.street == data.delivery.address.street
    assert customer.communication_preferences.newsletter is False
    assert customer.commercial.preferred_categories == ()
    assert customer.commercial.sales_channel is not None
    assert customer.commercial.sales_channel.code == "N13"
    assert customer.commercial.sales_channel.label == "Updated channel"
    assert customer.commercial.payment_days == 0
    assert customer.commercial.credit_granted == Decimal("12.30")
    assert customer.notes.items == ()
    assert customer.extensions.extra_data == {
        "keep": {"value": 1, "added": False},
        "items": [],
    }


@pytest.mark.anyio
async def test_create_and_read_do_not_share_mutable_customer_data(
    customer_data: IntegrationCustomerData,
) -> None:
    store = InMemoryCustomerSynchronizationStore()
    data = replace(
        customer_data,
        extensions=replace(customer_data.extensions, parameters={"nested": {"n": 1}}),
    )

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        first_id = await work.customers.create_customer(data)
        second_id = await work.customers.create_customer(customer_data)
        await work.commit()

    assert (first_id, second_id) == (1, 2)
    assert data.extensions.parameters is not None
    data.extensions.parameters["nested"]["n"] = 2

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        first = await work.customers.get_customer(first_id)
        assert first is not None
        assert first.extensions.parameters == {"nested": {"n": 1}}
        assert first.extensions.parameters is not None
        first.extensions.parameters["nested"]["n"] = 3
        assert await work.customers.get_customer(999) is None

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        first = await work.customers.get_customer(first_id)
        assert first is not None
        assert first.extensions.parameters == {"nested": {"n": 1}}


@pytest.mark.anyio
async def test_failure_after_commit_request_keeps_customer_and_event_unchanged(
    customer_data: IntegrationCustomerData,
) -> None:
    store = InMemoryCustomerSynchronizationStore()
    assert customer_data.registration.registered_at is not None
    created = CustomerCreatedEvent(
        schema_version=1,
        event_id=UUID("726c7c74-287d-44f2-b060-81fefa3d235d"),
        occurred_at=customer_data.registration.registered_at,
        resource_version=1,
        data=customer_data,
    )
    patch = CustomerUpdatedData(company=IntegrationCompanyPatch(name="New name"))
    updated = CustomerUpdatedEvent(
        schema_version=1,
        event_id=UUID("726c7c74-287d-44f2-b060-81fefa3d235e"),
        occurred_at=created.occurred_at,
        resource_version=2,
        reference_id=1,
        data=patch,
    )
    result = CustomerSynchronizationResult(success=True, reference_id=1)

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        await work.customers.create_customer(customer_data)
        await work.resource_versions.save_resource_version(1, 1)
        await work.processed_events.save_processed_result(created, result)
        await work.commit()

    with pytest.raises(RuntimeError, match="later failure"):
        async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
            await work.customers.update_customer(1, patch)
            await work.resource_versions.save_resource_version(1, 2)
            await work.processed_events.save_processed_result(updated, result)
            await work.commit()
            raise RuntimeError("later failure")

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) == customer_data
        assert await work.resource_versions.get_resource_version(1) == 1
        assert await work.processed_events.get_processed_result(created) == result
        assert await work.processed_events.get_processed_result(updated) is None


@pytest.mark.anyio
async def test_partial_patch_cannot_create_an_incomplete_nested_object(
    customer_data: IntegrationCustomerData,
) -> None:
    store = InMemoryCustomerSynchronizationStore()
    data = replace(
        customer_data,
        commercial=replace(customer_data.commercial, sales_channel=None),
    )

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        await work.customers.create_customer(data)
        await work.commit()

    with pytest.raises(CustomerSynchronizationConflictException):
        async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
            await work.customers.update_customer(
                1,
                CustomerUpdatedData(
                    commercial=IntegrationCommercialPatch(
                        sales_channel=IntegrationSalesChannelPatch(label="Only label")
                    )
                ),
            )

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) == data
