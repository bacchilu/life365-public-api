"""Full customer creation tests against a dedicated PostgreSQL database."""

import asyncio
import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
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
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.events import CustomerCreatedEvent
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNote,
    IntegrationCustomerNotes,
)
from app.application.exceptions import (
    CustomerSynchronizationConflictException,
    DBException,
    InvalidCustomerDataException,
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
_TEST_DATABASE_PREFIX = "life365_public_api_test_"
_KEY = b"test-customer-sync-hmac-key-32-bytes"
_TEST_TABLES = (
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
    if not conninfo_to_dict(url).get("dbname", "").startswith(_TEST_DATABASE_PREFIX):
        pytest.fail("Customer create tests require a dedicated test database")
    if os.environ.get("DATABASE_URL") == url:
        pytest.fail("Test database must differ from DATABASE_URL")

    with psycopg.connect(url, autocommit=True) as conn:
        database = conn.execute(sql.SQL("SELECT current_database()")).fetchone()
        assert database is not None
        existing = conn.execute(
            sql.SQL(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = ANY(%s)"
            ),
            (list(_TEST_TABLES),),
        ).fetchall()
        if not database[0].startswith(_TEST_DATABASE_PREFIX) or existing:
            pytest.fail("Customer create tests require an empty test database")

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


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


def _event(
    data: IntegrationCustomerData, event_number: int = 1
) -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=UUID(int=event_number),
        occurred_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
        resource_version=1,
        data=data,
    )


def _unit_of_work(url: str) -> PostgreSQLCustomerSynchronizationUnitOfWork:
    return PostgreSQLCustomerSynchronizationUnitOfWork(
        connection_string=url,
        fingerprint_secret=_KEY,
        customer_mapper_factory=lambda cur: PostgreSQLCustomerDataMapper(
            cur, registration_ip="203.0.113.42"
        ),
    )


def _counts(url: str) -> tuple[int, int, int]:
    with psycopg.connect(url) as conn:
        counts: list[int] = []
        for table in (
            "customers",
            "customer_synchronization_versions",
            "customer_synchronization_events",
        ):
            query = sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier("public", table)
            )
            row = conn.execute(query).fetchone()
            assert row is not None
            counts.append(row[0])
    return counts[0], counts[1], counts[2]


@pytest.mark.anyio
async def test_full_create_payload_writes_every_customer_section(
    test_database_url: str,
) -> None:
    result = await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(_event(_customer_data()))

    assert result.success is True
    assert result.reference_id > 0
    assert _counts(test_database_url) == (1, 1, 1)
    with psycopg.connect(test_database_url, row_factory=dict_row) as conn:
        row = conn.execute(
            sql.SQL("SELECT * FROM public.customers WHERE id = %s"),
            (result.reference_id,),
        ).fetchone()
        assert row is not None
        expected = {
            "login": "acme-italia",
            "pass": "initial-customer-password",
            "business_name": "ACME Italia SRL",
            "website": "https://www.acme.example",
            "phone": "+39 02 1234567",
            "phone2": None,
            "business_contact_name": "Mario Rossi",
            "email": "mario.rossi@acme.example",
            "additional_emails": [
                {
                    "email": "commerciale@acme.example",
                    "commercial": True,
                    "marketing": False,
                    "skype": None,
                }
            ],
            "pec": "acme@pec.example",
            "preferred_language": "it",
            "address_street": "Via Roma 10",
            "address_city": "Forli",
            "address_zip_code": "47121",
            "region_id": 158,
            "delivery_business_name": "ACME Italia - Warehouse",
            "delivery_contact_name": "Luigi Bianchi",
            "delivery_phone": "+39 02 7654321",
            "delivery_address": "Via Industriale 25",
            "delivery_city": "Forli",
            "delivery_zip_code": "47122",
            "delivery_region_id": 158,
            "fiscal_code": "RSSMRA80A01D704X",
            "vat_country": "IT",
            "vat_number": "12345678901",
            "vies": True,
            "fiscal_agent_code": None,
            "tax2": Decimal("0.00"),
            "newsletter": True,
            "reg_privacy": True,
            "reg_rules": True,
            "registration_date": datetime(2026, 9, 3, 12, 30),
            "registration_ip": "203.0.113.42",
            "verified": True,
            "last_login_date": None,
            "preferred_categories": [1, 14],
            "sales_channel_id": 13,
            "agent_id": 117,
            "payment_agreement": "Payment by bank transfer within 30 days",
            "preferred_payment_type": "BONIFICO",
            "payment_days": 30,
            "payment_days_eom": 0,
            "fido_granted": Decimal("10000.00"),
            "fido": Decimal("7500.00"),
            "payment_abi": "03069",
            "payment_cab": "09606",
            "payment_iban": "IT60X0542811101000000123456",
            "shop_location_lat": Decimal("44.2227390000"),
            "shop_location_lng": Decimal("12.0407310000"),
            "shop_group_ids": [3],
            "disable_box_discount": False,
            "disable_qty_delivery": False,
            "rma_prepaid": True,
            "disable_limit_sale": False,
            "_notes": [],
            "notes_open": 0,
            "admin_note": None,
            "parameters": None,
            "extra_data": None,
        }
        for column, value in expected.items():
            assert row[column] == value, column
        assert set(row) == {"id", *expected}

        stored = conn.execute(
            sql.SQL(
                "SELECT event_fingerprint FROM public.customer_synchronization_events"
            )
        ).fetchone()
        assert stored is not None
        assert len(stored["event_fingerprint"]) == 32


@pytest.mark.anyio
async def test_bad_field_rolls_back_customer_version_and_event(
    test_database_url: str,
) -> None:
    original = _customer_data()
    invalid = replace(original, company=replace(original.company, name="x" * 121))

    with pytest.raises(DBException):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(invalid))

    assert _counts(test_database_url) == (0, 0, 0)


@pytest.mark.anyio
async def test_unknown_region_rolls_back_the_event(test_database_url: str) -> None:
    original = _customer_data()
    invalid = replace(
        original,
        billing_address=replace(original.billing_address, region_name="Unknown"),
    )

    with pytest.raises(InvalidCustomerDataException, match="Unknown region"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(invalid))

    assert _counts(test_database_url) == (0, 0, 0)


@pytest.mark.anyio
async def test_failure_after_insert_rolls_back_every_write(
    test_database_url: str,
) -> None:
    with pytest.raises(RuntimeError, match="stop before commit"):
        async with _unit_of_work(test_database_url) as work:
            reference_id = await work.customers.create_customer(_customer_data())
            await work.resource_versions.save_resource_version(reference_id, 1)
            await work.commit()
            raise RuntimeError("stop before commit")

    assert _counts(test_database_url) == (0, 0, 0)


@pytest.mark.anyio
async def test_two_create_events_with_same_login_cannot_both_commit(
    test_database_url: str,
) -> None:
    first_event = _event(_customer_data(), event_number=1)
    second_event = _event(_customer_data(), event_number=2)

    async def deliver(event: CustomerCreatedEvent) -> object:
        return await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(event)

    results = await asyncio.gather(
        deliver(first_event), deliver(second_event), return_exceptions=True
    )

    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(
        isinstance(result, CustomerSynchronizationConflictException)
        for result in results
    ) == 1
    assert _counts(test_database_url) == (1, 1, 1)


@pytest.mark.anyio
async def test_nullable_references_and_nested_json_keep_their_values(
    test_database_url: str,
) -> None:
    original = _customer_data()
    data = replace(
        original,
        delivery=replace(original.delivery, address=None),
        commercial=replace(
            original.commercial,
            sales_channel=None,
            assigned_agent=None,
            preferred_categories=(),
            preferred_payment_type_code=None,
            credit_value=None,
        ),
        banking=replace(original.banking, iban=None),
        shop=replace(original.shop, latitude=None, longitude=None, groups=()),
        notes=IntegrationCustomerNotes(
            items=(
                IntegrationCustomerNote(
                    occurred_at=datetime(2026, 9, 3, 14, 30, tzinfo=UTC),
                    text="Call customer",
                    open=True,
                ),
            ),
            administrative_note="Review account",
        ),
        extensions=IntegrationCustomerExtensions(
            parameters={"flag": False, "nested": {"items": []}},
            extra_data={},
        ),
    )

    result = await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(_event(data))

    with psycopg.connect(test_database_url, row_factory=dict_row) as conn:
        row = conn.execute(
            sql.SQL("SELECT * FROM public.customers WHERE id = %s"),
            (result.reference_id,),
        ).fetchone()
        assert row is not None
        assert row["delivery_address"] is None
        assert row["delivery_region_id"] is None
        assert row["preferred_categories"] == []
        assert row["shop_group_ids"] == []
        assert row["sales_channel_id"] is None
        assert row["agent_id"] == 1
        assert row["preferred_payment_type"] is None
        assert row["fido"] is None
        assert row["payment_iban"] is None
        assert row["shop_location_lat"] is None
        assert row["shop_location_lng"] is None
        assert row["_notes"] == [
            {
                "date": "2026-09-03T14:30:00.000000+00:00",
                "note": "Call customer",
                "open": True,
            }
        ]
        assert row["notes_open"] == 1
        assert row["admin_note"] == "Review account"
        assert row["parameters"] == {"flag": False, "nested": {"items": []}}
        assert row["extra_data"] == {}


@pytest.mark.anyio
async def test_case_insensitive_duplicate_login_is_rejected(
    test_database_url: str,
) -> None:
    first = _customer_data()
    await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(_event(first))
    duplicate = replace(
        first, credentials=replace(first.credentials, login="  ACME-ITALIA  ")
    )

    with pytest.raises(CustomerSynchronizationConflictException, match="login"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(duplicate, event_number=2))

    assert _counts(test_database_url) == (1, 1, 1)


@pytest.mark.anyio
async def test_invalid_iban_or_credit_value_leaves_no_rows(
    test_database_url: str,
) -> None:
    original = _customer_data()
    invalid_iban = replace(
        original, banking=replace(original.banking, iban="NOT-AN-IBAN")
    )
    with pytest.raises(InvalidCustomerDataException, match="banking.iban"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(invalid_iban))

    invalid_credit = replace(
        original,
        commercial=replace(original.commercial, credit_value=Decimal("7500.001")),
    )
    with pytest.raises(InvalidCustomerDataException, match="creditValue"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(invalid_credit, event_number=2))

    assert _counts(test_database_url) == (0, 0, 0)


@pytest.mark.anyio
async def test_blank_login_and_missing_tax_identity_leave_no_rows(
    test_database_url: str,
) -> None:
    original = _customer_data()
    blank_login = replace(
        original, credentials=replace(original.credentials, login="   ")
    )
    with pytest.raises(InvalidCustomerDataException, match="login"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(blank_login))

    missing_tax = replace(
        original,
        tax_profile=replace(
            original.tax_profile, fiscal_code=None, vat_number=None
        ),
    )
    with pytest.raises(InvalidCustomerDataException, match="fiscal code or VAT"):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(_event(missing_tax, event_number=2))

    assert _counts(test_database_url) == (0, 0, 0)
