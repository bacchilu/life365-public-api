import json
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.application import dtos

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PATH = (
    _PROJECT_ROOT / "tests/fixtures/integrations/salesforce/customer-created-v1.json"
)


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


def _python_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower(): value
        for name, value in data.items()
    }


@pytest.fixture
def customer(payload: dict[str, Any]) -> dtos.IntegrationCustomerData:
    contact = _python_fields(payload["primaryContact"])
    contact["additional_emails"] = tuple(
        dtos.IntegrationAdditionalEmail(**item) for item in contact["additional_emails"]
    )
    delivery = _python_fields(payload["delivery"])
    delivery["address"] = dtos.IntegrationAddress(**_python_fields(delivery["address"]))
    tax = _python_fields(payload["taxProfile"])
    tax["secondary_tax_value"] = Decimal(tax["secondary_tax_value"])
    registration = _python_fields(payload["registration"])
    registration["registered_at"] = datetime.fromisoformat(
        registration["registered_at"]
    )
    commercial = _python_fields(payload["commercial"])
    commercial["preferred_categories"] = tuple(
        dtos.IntegrationCategory(**item) for item in commercial["preferred_categories"]
    )
    commercial["sales_channel"] = dtos.IntegrationSalesChannel(
        **commercial["sales_channel"]
    )
    commercial["assigned_agent"] = dtos.IntegrationAgent(
        **_python_fields(commercial["assigned_agent"])
    )
    commercial["credit_granted"] = Decimal(commercial["credit_granted"])
    commercial["credit_value"] = Decimal(commercial["credit_value"])
    shop = _python_fields(payload["shop"])
    shop["groups"] = tuple(dtos.IntegrationShopGroup(**item) for item in shop["groups"])
    notes = _python_fields(payload["notes"])
    notes["items"] = tuple(
        dtos.IntegrationCustomerNote(
            occurred_at=datetime.fromisoformat(item["occurredAt"]),
            text=item["text"],
            open=item["open"],
        )
        for item in notes["items"]
    )
    return dtos.IntegrationCustomerData(
        credentials=dtos.IntegrationCustomerCredentials(**payload["credentials"]),
        company=dtos.IntegrationCompany(**_python_fields(payload["company"])),
        primary_contact=dtos.IntegrationPrimaryContact(**contact),
        billing_address=dtos.IntegrationAddress(
            **_python_fields(payload["billingAddress"])
        ),
        delivery=dtos.IntegrationDelivery(**delivery),
        tax_profile=dtos.IntegrationTaxProfile(**tax),
        communication_preferences=dtos.IntegrationCommunicationPreferences(
            **_python_fields(payload["communicationPreferences"])
        ),
        registration=dtos.IntegrationRegistration(**registration),
        commercial=dtos.IntegrationCommercial(**commercial),
        banking=dtos.IntegrationBanking(**payload["banking"]),
        shop=dtos.IntegrationShop(**shop),
        operational_settings=dtos.IntegrationOperationalSettings(
            **_python_fields(payload["operationalSettings"])
        ),
        notes=dtos.IntegrationCustomerNotes(**notes),
        extensions=dtos.IntegrationCustomerExtensions(
            **_python_fields(payload["extensions"])
        ),
    )


def _contract_value(value: object) -> Any:
    """Compare application values with the fixture without an API serializer."""
    if is_dataclass(value) and not isinstance(value, type):
        result = {}
        for field in fields(value):
            first, *rest = field.name.split("_")
            name = first + "".join(part.title() for part in rest)
            result[name] = _contract_value(getattr(value, field.name))
        return result
    if isinstance(value, tuple):
        return [_contract_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def _nested_dtos(value: object) -> Iterator[Any]:
    if is_dataclass(value) and not isinstance(value, type):
        yield value
        for field in fields(value):
            yield from _nested_dtos(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:
            yield from _nested_dtos(item)


def test_complete_dto_preserves_canonical_payload(
    customer: dtos.IntegrationCustomerData, payload: dict[str, Any]
) -> None:
    assert json.loads(json.dumps(_contract_value(customer))) == payload


def test_all_nested_dtos_are_frozen_slotted_and_exported(
    customer: dtos.IntegrationCustomerData,
) -> None:
    note = dtos.IntegrationCustomerNote(
        occurred_at=datetime.fromisoformat("2026-09-03T12:30:00+00:00"),
        text="Synthetic note",
        open=True,
    )
    customer = replace(customer, notes=replace(customer.notes, items=(note,)))

    for instance in _nested_dtos(customer):
        cls = type(instance)
        assert getattr(dtos, cls.__name__) is cls
        assert cls.__name__ in dtos.__all__
        assert not hasattr(instance, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(instance, fields(instance)[0].name, None)
        for field in fields(instance):
            assert field.default is MISSING
            assert field.default_factory is MISSING


def test_password_is_available_but_absent_from_representations(
    customer: dtos.IntegrationCustomerData, payload: dict[str, Any]
) -> None:
    password = payload["credentials"]["password"]
    assert customer.credentials.password == password
    for value in (customer, customer.credentials):
        assert password not in repr(value)
        assert password not in str(value)


def test_financial_values_preserve_decimal_precision(
    customer: dtos.IntegrationCustomerData,
) -> None:
    exact_value = "12345678901234567890.12345678901234567890"
    customer = replace(
        customer,
        commercial=replace(
            customer.commercial,
            credit_granted=Decimal(exact_value),
            credit_value=Decimal("0.10"),
        ),
    )
    data = _contract_value(customer)

    assert data["commercial"]["creditGranted"] == exact_value
    assert data["commercial"]["creditValue"] == "0.10"
    assert data["taxProfile"]["secondaryTaxValue"] == "0.00"


def test_registration_and_notes_preserve_timezone_information(
    customer: dtos.IntegrationCustomerData,
) -> None:
    timestamp = "2026-09-15T10:15:30.123456+02:00"
    instant = datetime.fromisoformat(timestamp)
    customer = replace(
        customer,
        registration=replace(
            customer.registration, registered_at=instant, last_login_at=instant
        ),
        notes=dtos.IntegrationCustomerNotes(
            items=(dtos.IntegrationCustomerNote(instant, "Call customer", True),),
            administrative_note="Synthetic administrative note",
        ),
    )
    data = _contract_value(customer)

    assert instant.utcoffset() == timedelta(hours=2)
    assert data["registration"]["registeredAt"] == timestamp
    assert data["registration"]["lastLoginAt"] == timestamp
    assert data["notes"] == {
        "items": [{"occurredAt": timestamp, "text": "Call customer", "open": True}],
        "administrativeNote": "Synthetic administrative note",
    }


@pytest.mark.parametrize("preference", [True, False, None])
def test_nullable_booleans_preserve_all_three_states(
    customer: dtos.IntegrationCustomerData, preference: bool | None
) -> None:
    preferences = dtos.IntegrationCommunicationPreferences(
        newsletter=preference,
        privacy_registered=preference,
        rules_registered=preference,
    )
    customer = replace(customer, communication_preferences=preferences)

    for value in _contract_value(customer)["communicationPreferences"].values():
        assert value is preference


def test_nullable_references_and_empty_collections_are_representable(
    customer: dtos.IntegrationCustomerData,
) -> None:
    customer = replace(
        customer,
        commercial=replace(
            customer.commercial,
            assigned_agent=None,
            sales_channel=None,
            preferred_categories=(),
        ),
        delivery=replace(customer.delivery, address=None),
        primary_contact=replace(customer.primary_contact, additional_emails=()),
        shop=replace(customer.shop, groups=()),
    )
    data = _contract_value(customer)

    assert data["commercial"]["assignedAgent"] is None
    assert data["commercial"]["salesChannel"] is None
    assert data["commercial"]["preferredCategories"] == []
    assert data["delivery"]["address"] is None
    assert data["primaryContact"]["additionalEmails"] == []
    assert data["shop"]["groups"] == []
    assert data["notes"]["items"] == []


def test_extensions_preserve_arbitrary_nested_json(
    customer: dtos.IntegrationCustomerData,
) -> None:
    parameters = {"custom_key": {"values": [True, None, 12, 2.5, "text"]}}
    extra_data = {"externalLabel": "Sample", "nested": [{"keep_key": None}]}
    customer = replace(
        customer,
        extensions=dtos.IntegrationCustomerExtensions(parameters, extra_data),
    )

    assert json.loads(json.dumps(_contract_value(customer)))["extensions"] == {
        "parameters": parameters,
        "extraData": extra_data,
    }


def test_dtos_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "from app.application.dtos import IntegrationCustomerData",
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
