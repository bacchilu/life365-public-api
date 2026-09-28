"""Offline tests for direct PostgreSQL customer create values."""

import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequestData,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerNote,
    IntegrationCustomerNotes,
)
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.create_values import (
    create_customer_direct_values,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


def test_create_values_map_the_complete_fixture_direct_fields() -> None:
    values = create_customer_direct_values(_customer_data())

    assert values["login"] == "acme-italia"
    assert values["pass"] == "initial-customer-password"
    assert values["business_name"] == "ACME Italia SRL"
    assert values["business_contact_name"] == "Mario Rossi"
    assert values["email"] == "mario.rossi@acme.example"
    assert values["address_street"] == "Via Roma 10"
    assert values["delivery_address"] == "Via Industriale 25"
    assert values["delivery_zip_code"] == "47122"
    assert values["vies"] is True
    assert values["vat_country"] == "IT"
    assert values["tax2"] == Decimal("0.00")
    assert values["fido_granted"] == Decimal("10000.00")
    assert values["fido"] == Decimal("7500.00")
    assert values["payment_abi"] == "03069"
    assert values["payment_iban"] == "IT60X0542811101000000123456"
    assert values["shop_location_lat"] == Decimal("44.2227390000")
    assert values["shop_location_lng"] == Decimal("12.0407310000")
    assert values["registration_date"] == datetime(2026, 9, 3, 12, 30)
    assert values["last_login_date"] is None
    assert values["disable_box_discount"] is False
    assert values["notes_open"] == 0
    assert values["admin_note"] is None
    assert values["parameters"] is None
    assert values["extra_data"] is None

    additional_emails = values["additional_emails"]
    notes = values["_notes"]
    assert isinstance(additional_emails, Jsonb)
    assert additional_emails.obj == [
        {
            "email": "commerciale@acme.example",
            "commercial": True,
            "marketing": False,
            "skype": None,
        }
    ]
    assert isinstance(notes, Jsonb)
    assert notes.obj == []


def test_create_values_map_notes_and_clear_nullable_delivery_address() -> None:
    original = _customer_data()
    registered_at = original.registration.registered_at
    assert registered_at is not None
    note = IntegrationCustomerNote(
        occurred_at=registered_at,
        text="Call customer",
        open=True,
    )
    data = replace(
        original,
        credentials=replace(original.credentials, login="  Acme-Italia  "),
        delivery=replace(original.delivery, address=None),
        notes=IntegrationCustomerNotes(
            items=(note,), administrative_note="Account note"
        ),
    )

    values = create_customer_direct_values(data)

    assert values["login"] == "Acme-Italia"
    assert values["delivery_address"] is None
    assert values["delivery_city"] is None
    assert values["delivery_zip_code"] is None
    assert values["notes_open"] == 1
    assert values["admin_note"] == "Account note"
    notes = values["_notes"]
    assert isinstance(notes, Jsonb)
    assert notes.obj == [
        {
            "date": "2026-09-03T12:30:00.000000+00:00",
            "note": "Call customer",
            "open": True,
        }
    ]


def test_create_values_leave_reference_and_undecided_columns_to_the_mapper() -> None:
    values = create_customer_direct_values(_customer_data())

    assert not {
        "id",
        "region_id",
        "delivery_region_id",
        "agent_id",
        "preferred_categories",
        "sales_channel_id",
        "preferred_payment_type",
        "shop_group_ids",
        "registration_ip",
    } & values.keys()


def test_null_shop_coordinates_remain_sql_null() -> None:
    original = _customer_data()
    data = replace(
        original,
        shop=replace(original.shop, latitude=None, longitude=None),
    )

    values = create_customer_direct_values(data)

    assert values["shop_location_lat"] is None
    assert values["shop_location_lng"] is None


def test_invalid_shop_coordinate_is_rejected_before_insert() -> None:
    original = _customer_data()
    data = replace(original, shop=replace(original.shop, latitude=90.1))

    with pytest.raises(InvalidCustomerDataException, match="latitude"):
        create_customer_direct_values(data)
