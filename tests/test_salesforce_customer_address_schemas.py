import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.api.integrations.schemas.address import (
    IntegrationAddress,
    IntegrationDelivery,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_MODELS: dict[str, type[BaseModel]] = {
    "billingAddress": IntegrationAddress,
    "delivery": IntegrationDelivery,
}
_NULLABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "billingAddress": ("postalCode",),
    "delivery": ("businessName", "contactName", "phone", "address"),
}
_STRING_LIMITS = (
    ("billingAddress", "street", 100),
    ("billingAddress", "city", 50),
    ("billingAddress", "postalCode", 50),
    ("delivery", "businessName", 120),
    ("delivery", "contactName", 100),
    ("delivery", "phone", 50),
)


@pytest.fixture
def payload() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]


@pytest.mark.parametrize("section", _MODELS)
def test_address_sections_preserve_canonical_json(
    section: str,
    payload: dict[str, Any],
) -> None:
    result = _MODELS[section].model_validate_json(json.dumps(payload[section]))

    assert result.model_dump(mode="json", by_alias=True) == payload[section]


@pytest.mark.parametrize("section", _MODELS)
def test_all_address_create_fields_are_required(
    section: str,
    payload: dict[str, Any],
) -> None:
    for field_name in payload[section]:
        incomplete = {
            key: value for key, value in payload[section].items() if key != field_name
        }

        with pytest.raises(ValidationError) as error:
            _MODELS[section].model_validate(incomplete)

        assert error.value.errors()[0]["loc"] == (field_name,)
        assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("section", _MODELS)
def test_only_documented_address_fields_accept_null(
    section: str,
    payload: dict[str, Any],
) -> None:
    for field_name in payload[section]:
        data = {**payload[section], field_name: None}
        if field_name in _NULLABLE_FIELDS[section]:
            result = _MODELS[section].model_validate(data)
            assert result.model_dump(by_alias=True)[field_name] is None
        else:
            with pytest.raises(ValidationError) as error:
                _MODELS[section].model_validate(data)
            assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize("section", _MODELS)
def test_unknown_address_fields_are_rejected(
    section: str,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        _MODELS[section].model_validate({**payload[section], "unknown": True})

    assert error.value.errors()[0]["loc"] == ("unknown",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("section", _MODELS)
def test_address_json_schema_uses_required_camel_case_fields(
    section: str,
    payload: dict[str, Any],
) -> None:
    schema = _MODELS[section].model_json_schema()

    assert set(schema["properties"]) == set(payload[section])
    assert set(schema["required"]) == set(payload[section])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(("section", "field_name", "limit"), _STRING_LIMITS)
def test_address_string_limits_accept_boundary_and_reject_overflow(
    section: str,
    field_name: str,
    limit: int,
    payload: dict[str, Any],
) -> None:
    model = _MODELS[section]
    result = model.model_validate({**payload[section], field_name: "x" * limit})
    assert result.model_dump(by_alias=True)[field_name] == "x" * limit

    with pytest.raises(ValidationError) as error:
        model.model_validate({**payload[section], field_name: "x" * (limit + 1)})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize(("section", "field_name", "_limit"), _STRING_LIMITS)
@pytest.mark.parametrize("value", [0, False, b"text"])
def test_address_string_fields_reject_other_types(
    section: str,
    field_name: str,
    _limit: int,
    value: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        _MODELS[section].model_validate({**payload[section], field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "string_type"


@pytest.mark.parametrize(
    "country_code",
    ["it", "ITA", "I", "", "I1", " IT", "IT ", "IT\n", 12, None],
)
def test_country_code_rejects_non_uppercase_iso_shape(
    country_code: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationAddress.model_validate(
            {**payload["billingAddress"], "countryCode": country_code}
        )

    assert error.value.errors()[0]["loc"] == ("countryCode",)


@pytest.mark.parametrize("country_code", ["IT", "FR", "PL"])
def test_country_code_accepts_two_uppercase_letters(
    country_code: str,
    payload: dict[str, Any],
) -> None:
    result = IntegrationAddress.model_validate(
        {**payload["billingAddress"], "countryCode": country_code}
    )

    assert result.country_code == country_code


@pytest.mark.parametrize(
    "region_name",
    ["Forlì-Cesena", "Venezia - laguna", "Roma - fuori GRA"],
)
def test_region_name_preserves_exact_catalog_text(
    region_name: str,
    payload: dict[str, Any],
) -> None:
    result = IntegrationAddress.model_validate(
        {**payload["billingAddress"], "regionName": region_name}
    )

    assert result.region_name == region_name


def test_delivery_rejects_unknown_nested_address_fields(
    payload: dict[str, Any],
) -> None:
    address = {**payload["delivery"]["address"], "regionCode": "IT-FC"}

    with pytest.raises(ValidationError) as error:
        IntegrationDelivery.model_validate({**payload["delivery"], "address": address})

    assert error.value.errors()[0]["loc"] == ("address", "regionCode")
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_delivery_requires_complete_address_when_present(
    payload: dict[str, Any],
) -> None:
    address = {
        key: value
        for key, value in payload["delivery"]["address"].items()
        if key != "regionName"
    }

    with pytest.raises(ValidationError) as error:
        IntegrationDelivery.model_validate({**payload["delivery"], "address": address})

    assert error.value.errors()[0]["loc"] == ("address", "regionName")
    assert error.value.errors()[0]["type"] == "missing"


def test_delivery_can_clear_all_nullable_values() -> None:
    result = IntegrationDelivery.model_validate(
        {
            "businessName": None,
            "contactName": None,
            "phone": None,
            "address": None,
        }
    )

    assert result.business_name is None
    assert result.contact_name is None
    assert result.phone is None
    assert result.address is None


def test_delivery_schema_exposes_closed_nested_address() -> None:
    schema = IntegrationDelivery.model_json_schema()

    assert schema["$defs"]["IntegrationAddress"]["additionalProperties"] is False
