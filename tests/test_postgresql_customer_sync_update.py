"""Customer patch behavior against an isolated PostgreSQL database."""

import asyncio
import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

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
from app.application.dtos.customer_integration.finance_patch import (
    IntegrationTaxProfilePatch,
)
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNote,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
    IntegrationOperationalSettingsPatch,
    IntegrationShopPatch,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
)
from app.application.exceptions import (
    CustomerSynchronizationConflictException,
    DBException,
    InvalidCustomerDataException,
    StaleCustomerVersionException,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_sync.customers import (
    PostgreSQLCustomerDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = (
    _ROOT / "tests/fixtures/integrations/salesforce/customer-sync-create-schema.sql"
)
_MIGRATION = _ROOT / "migrations/0001_customer_synchronization.sql"
_FIXTURE = _ROOT / "tests/fixtures/integrations/salesforce/customer-created-v1.json"
_KEY = b"test-customer-sync-hmac-key-32-bytes"
_TABLES = (
    "customer_synchronization_events",
    "customer_synchronization_versions",
    "customers",
    "regions",
    "countries",
    "categories",
    "agents",
    "sales_channels",
    "payment_types",
    "shop_groups",
)


@pytest.fixture
def test_database_url() -> Iterator[str]:
    url = os.environ.get("CUSTOMER_SYNC_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("Set CUSTOMER_SYNC_TEST_DATABASE_URL to an isolated database")
    if not conninfo_to_dict(url).get("dbname", "").startswith(
        "life365_public_api_test_"
    ) or os.environ.get("DATABASE_URL") == url:
        pytest.fail("Customer update tests require a dedicated test database")

    with psycopg.connect(url, autocommit=True) as conn:
        existing = conn.execute(
            sql.SQL(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = ANY(%s)"
            ),
            (list(_TABLES),),
        ).fetchall()
        if existing:
            pytest.fail("Customer update tests require an empty test database")
        try:
            conn.execute(_SCHEMA.read_text(encoding="utf-8"))
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))
            yield url
        finally:
            conn.execute(
                sql.SQL(
                    "DROP TABLE IF EXISTS "
                    "public.customer_synchronization_events, "
                    "public.customer_synchronization_versions, "
                    "public.customers, public.regions, public.countries, "
                    "public.categories, public.agents, public.sales_channels, "
                    "public.payment_types, public.shop_groups CASCADE"
                )
            )


def _unit_of_work(url: str) -> PostgreSQLCustomerSynchronizationUnitOfWork:
    return PostgreSQLCustomerSynchronizationUnitOfWork(
        connection_string=url,
        fingerprint_secret=_KEY,
        customer_mapper_factory=lambda cur: PostgreSQLCustomerDataMapper(
            cur, registration_ip="203.0.113.42"
        ),
    )


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


def _create_event(data: IntegrationCustomerData, number: int) -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=UUID(int=number),
        occurred_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
        resource_version=1,
        data=data,
    )


def _update_event(
    reference_id: int, version: int, data: CustomerUpdatedData, number: int
) -> CustomerUpdatedEvent:
    return CustomerUpdatedEvent(
        schema_version=1,
        event_id=UUID(int=number),
        occurred_at=datetime(2026, 9, 25, 10, version, tzinfo=UTC),
        resource_version=version,
        reference_id=reference_id,
        data=data,
    )


async def _create_customer(
    url: str, data: IntegrationCustomerData | None = None, *, number: int = 1
) -> int:
    result = await CustomerSynchronizationService(
        _unit_of_work(url)
    ).synchronize_customer(
        _create_event(data if data is not None else _customer_data(), number)
    )
    return result.reference_id


def _state(url: str, reference_id: int) -> tuple[dict[str, Any], int, int]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        row = conn.execute(
            sql.SQL("SELECT * FROM public.customers WHERE id = %s"),
            (reference_id,),
        ).fetchone()
        assert row is not None
        version = conn.execute(
            sql.SQL(
                "SELECT resource_version FROM public.customer_synchronization_versions "
                "WHERE customer_id = %s"
            ),
            (reference_id,),
        ).fetchone()
        assert version is not None
        count = conn.execute(
            sql.SQL("SELECT count(*) AS n FROM public.customer_synchronization_events")
        ).fetchone()
        assert count is not None
        return row, version["resource_version"], count["n"]


@pytest.mark.anyio
async def test_partial_patch_preserves_siblings_and_merges_json(
    test_database_url: str,
) -> None:
    original = _customer_data()
    data = replace(
        original,
        extensions=IntegrationCustomerExtensions(
            parameters={
                "unknown": "keep",
                "nested": {"keep": 1, "remove": "old", "list": [1]},
            },
            extra_data={"old": True},
        ),
    )
    reference_id = await _create_customer(test_database_url, data)
    before, _, _ = _state(test_database_url, reference_id)

    patch = CustomerUpdatedData(
        company=IntegrationCompanyPatch(
            name="ACME Updated", website=None, secondary_phone=""
        ),
        primary_contact=IntegrationPrimaryContactPatch(additional_emails=()),
        billing_address=IntegrationAddressPatch(street="Via Nuova 12"),
        commercial=IntegrationCommercialPatch(
            preferred_categories=(), credit_value=Decimal("0"), payment_days=0
        ),
        shop=IntegrationShopPatch(groups=(), latitude=0.0),
        operational_settings=IntegrationOperationalSettingsPatch(
            disable_box_discount=True, disable_quantity_delivery=False
        ),
        notes=IntegrationCustomerNotesPatch(
            items=(
                IntegrationCustomerNote(
                    occurred_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
                    text="Call",
                    open=True,
                ),
            ),
            administrative_note="",
        ),
        extensions=IntegrationCustomerExtensionsPatch(
            parameters={"nested": {"remove": None, "list": [], "flag": False}},
            extra_data=None,
        ),
    )
    await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(_update_event(reference_id, 2, patch, 2))

    after, version, count = _state(test_database_url, reference_id)
    assert (version, count) == (2, 2)
    assert after["business_name"] == "ACME Updated"
    assert after["website"] is None
    assert after["phone2"] == ""
    assert after["additional_emails"] == []
    assert after["address_street"] == "Via Nuova 12"
    assert after["preferred_categories"] == []
    assert after["fido"] == Decimal("0.00")
    assert after["payment_days"] == 0
    assert after["shop_group_ids"] == []
    assert after["shop_location_lat"] == Decimal("0.0000000000")
    assert after["disable_box_discount"] is True
    assert after["disable_qty_delivery"] is False
    assert after["notes_open"] == 1
    assert len(after["_notes"]) == 1
    assert after["admin_note"] == ""
    assert after["parameters"] == {
        "unknown": "keep",
        "nested": {"keep": 1, "list": [], "flag": False},
    }
    assert after["extra_data"] is None
    for column in ("phone", "email", "address_city", "region_id", "agent_id"):
        assert after[column] == before[column]


@pytest.mark.anyio
async def test_address_and_reference_changes_are_explicit(
    test_database_url: str,
) -> None:
    reference_id = await _create_customer(test_database_url)
    with psycopg.connect(test_database_url) as conn:
        conn.execute(
            sql.SQL(
                "INSERT INTO public.regions (id, country_id, region_name, enabled) "
                "VALUES (159, 1, 'Roma', true)"
            )
        )

    first = CustomerUpdatedData(
        delivery=IntegrationDeliveryPatch(address=None),
        commercial=IntegrationCommercialPatch(
            sales_channel=None, assigned_agent=None, preferred_payment_type_code=None
        ),
    )
    service = CustomerSynchronizationService(_unit_of_work(test_database_url))
    await service.synchronize_customer(_update_event(reference_id, 2, first, 2))
    row, _, _ = _state(test_database_url, reference_id)
    assert row["delivery_address"] is None
    assert row["delivery_city"] is None
    assert row["delivery_region_id"] is None
    assert row["sales_channel_id"] is None
    assert row["agent_id"] == 1
    assert row["preferred_payment_type"] is None

    second = CustomerUpdatedData(
        billing_address=IntegrationAddressPatch(region_name="Roma"),
        delivery=IntegrationDeliveryPatch(
            address=IntegrationAddressPatch(
                street="Via Nuova 1",
                city="Roma",
                postal_code=None,
                country_code="IT",
                region_name="Roma",
            )
        ),
        commercial=IntegrationCommercialPatch(
            sales_channel=IntegrationSalesChannelPatch(
                code="N13", label="IT Distribution"
            )
        ),
    )
    await service.synchronize_customer(_update_event(reference_id, 3, second, 3))
    row, version, count = _state(test_database_url, reference_id)
    assert (version, count) == (3, 3)
    assert row["region_id"] == 159
    assert row["address_street"] == "Via Roma 10"
    assert row["delivery_address"] == "Via Nuova 1"
    assert row["delivery_region_id"] == 159
    assert row["sales_channel_id"] == 13


@pytest.mark.anyio
async def test_invalid_patch_or_failed_sql_leaves_row_and_event_unchanged(
    test_database_url: str,
) -> None:
    reference_id = await _create_customer(test_database_url)
    before = _state(test_database_url, reference_id)
    service = CustomerSynchronizationService(_unit_of_work(test_database_url))

    with pytest.raises(InvalidCustomerDataException, match="category"):
        await service.synchronize_customer(
            _update_event(
                reference_id,
                2,
                CustomerUpdatedData(
                    company=IntegrationCompanyPatch(name="Should not persist"),
                    commercial=IntegrationCommercialPatch(
                        preferred_categories=(
                            replace(
                                _customer_data().commercial.preferred_categories[0],
                                code="bad",
                            ),
                        )
                    ),
                ),
                2,
            )
        )
    assert _state(test_database_url, reference_id) == before

    with pytest.raises(DBException):
        await service.synchronize_customer(
            _update_event(
                reference_id,
                2,
                CustomerUpdatedData(company=IntegrationCompanyPatch(name="X" * 121)),
                3,
            )
        )
    assert _state(test_database_url, reference_id) == before

    with pytest.raises(InvalidCustomerDataException, match="fiscal code or VAT"):
        await service.synchronize_customer(
            _update_event(
                reference_id,
                2,
                CustomerUpdatedData(
                    tax_profile=IntegrationTaxProfilePatch(
                        fiscal_code=None, vat_number=None
                    )
                ),
                4,
            )
        )
    assert _state(test_database_url, reference_id) == before


@pytest.mark.anyio
async def test_failure_after_update_rolls_back_customer_and_version(
    test_database_url: str,
) -> None:
    reference_id = await _create_customer(test_database_url)
    before = _state(test_database_url, reference_id)

    with pytest.raises(RuntimeError, match="stop before commit"):
        async with _unit_of_work(test_database_url) as work:
            await work.customers.update_customer(
                reference_id,
                CustomerUpdatedData(company=IntegrationCompanyPatch(name="Temporary")),
            )
            await work.resource_versions.save_resource_version(reference_id, 2)
            await work.commit()
            raise RuntimeError("stop before commit")

    assert _state(test_database_url, reference_id) == before


@pytest.mark.anyio
async def test_concurrent_updates_reject_the_stale_version(
    test_database_url: str,
) -> None:
    reference_id = await _create_customer(test_database_url)
    first = _update_event(
        reference_id, 2,
        CustomerUpdatedData(company=IntegrationCompanyPatch(name="First")), 2
    )
    second = _update_event(
        reference_id, 2,
        CustomerUpdatedData(company=IntegrationCompanyPatch(name="Second")), 3
    )

    async def deliver(event: CustomerUpdatedEvent) -> CustomerSynchronizationResult:
        return await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(event)

    results = await asyncio.gather(
        deliver(first), deliver(second), return_exceptions=True
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(
        isinstance(result, StaleCustomerVersionException) for result in results
    ) == 1
    row, version, count = _state(test_database_url, reference_id)
    assert row["business_name"] in ("First", "Second")
    assert (version, count) == (2, 2)


@pytest.mark.anyio
async def test_login_update_keeps_own_name_but_rejects_another_customer(
    test_database_url: str,
) -> None:
    first_id = await _create_customer(test_database_url)
    other = _customer_data()
    other = replace(other, credentials=replace(other.credentials, login="other-login"))
    second_id = await _create_customer(test_database_url, other, number=2)

    service = CustomerSynchronizationService(_unit_of_work(test_database_url))
    await service.synchronize_customer(
        _update_event(
            first_id, 2,
            CustomerUpdatedData(
                credentials=IntegrationCustomerCredentialsPatch(login=" ACME-ITALIA ")
            ), 3
        )
    )
    with pytest.raises(CustomerSynchronizationConflictException, match="login"):
        await service.synchronize_customer(
            _update_event(
                second_id, 2,
                CustomerUpdatedData(
                    credentials=IntegrationCustomerCredentialsPatch(login="acme-italia")
                ), 4
            )
        )
    first, _, _ = _state(test_database_url, first_id)
    second, second_version, count = _state(test_database_url, second_id)
    assert first["login"] == "ACME-ITALIA"
    assert second["login"] == "other-login"
    assert (second_version, count) == (1, 3)
