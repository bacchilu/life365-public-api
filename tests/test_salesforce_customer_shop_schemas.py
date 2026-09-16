import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.api.integrations.schemas.shop import (
    IntegrationOperationalSettings,
    IntegrationShop,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_MODELS: dict[str, type[BaseModel]] = {
    "shop": IntegrationShop,
    "operationalSettings": IntegrationOperationalSettings,
}
_NULLABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "shop": ("latitude", "longitude"),
    "operationalSettings": (
        "disableQuantityDelivery",
        "prepaidReturns",
        "disableSaleLimit",
    ),
}


@pytest.fixture
def payload() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]


@pytest.mark.parametrize("section", _MODELS)
def test_shop_sections_preserve_canonical_json(
    section: str,
    payload: dict[str, Any],
) -> None:
    result = _MODELS[section].model_validate_json(json.dumps(payload[section]))

    assert result.model_dump(mode="json", by_alias=True) == payload[section]


@pytest.mark.parametrize("section", _MODELS)
def test_all_shop_create_fields_are_required(
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
def test_only_documented_shop_fields_accept_null(
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
def test_unknown_shop_fields_are_rejected(
    section: str,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        _MODELS[section].model_validate({**payload[section], "unknown": True})

    assert error.value.errors()[0]["loc"] == ("unknown",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("section", _MODELS)
def test_shop_json_schema_uses_required_contract_fields(
    section: str,
    payload: dict[str, Any],
) -> None:
    schema = _MODELS[section].model_json_schema()

    assert set(schema["properties"]) == set(payload[section])
    assert set(schema["required"]) == set(payload[section])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("latitude", -90),
        ("latitude", 0),
        ("latitude", 90),
        ("longitude", -180),
        ("longitude", 0),
        ("longitude", 180),
    ],
)
def test_coordinates_accept_inclusive_boundaries(
    field_name: str,
    value: int,
    payload: dict[str, Any],
) -> None:
    result = IntegrationShop.model_validate({**payload["shop"], field_name: value})

    assert getattr(result, field_name) == value


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("latitude", -90.0000000001),
        ("latitude", 90.0000000001),
        ("longitude", -180.0000000001),
        ("longitude", 180.0000000001),
    ],
)
def test_coordinates_reject_values_outside_geographic_ranges(
    field_name: str,
    value: float,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate({**payload["shop"], field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize("field_name", ["latitude", "longitude"])
@pytest.mark.parametrize("value", ["1.25", True, False, float("inf"), float("nan")])
def test_coordinates_reject_non_finite_or_non_numeric_values(
    field_name: str,
    value: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate({**payload["shop"], field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize("field_name", ["latitude", "longitude"])
def test_coordinates_allow_at_most_ten_decimal_places(
    field_name: str,
    payload: dict[str, Any],
) -> None:
    result = IntegrationShop.model_validate(
        {**payload["shop"], field_name: 1.1234567890}
    )
    assert getattr(result, field_name) == 1.1234567890

    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate({**payload["shop"], field_name: 1.12345678901})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "value_error"


def test_shop_groups_accept_an_empty_array(payload: dict[str, Any]) -> None:
    result = IntegrationShop.model_validate({**payload["shop"], "groups": []})

    assert result.groups == []


def test_shop_groups_require_a_json_array(payload: dict[str, Any]) -> None:
    groups = tuple(payload["shop"]["groups"])

    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate({**payload["shop"], "groups": groups})

    assert error.value.errors()[0]["loc"] == ("groups",)
    assert error.value.errors()[0]["type"] == "list_type"


@pytest.mark.parametrize("field_name", ["code", "label"])
def test_all_shop_group_fields_are_required(
    field_name: str,
    payload: dict[str, Any],
) -> None:
    data = deepcopy(payload["shop"])
    del data["groups"][0][field_name]

    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("groups", 0, field_name)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field_name", ["code", "label"])
@pytest.mark.parametrize("value", ["", 1, False])
def test_shop_group_identity_requires_nonempty_strings(
    field_name: str,
    value: object,
    payload: dict[str, Any],
) -> None:
    data = deepcopy(payload["shop"])
    data["groups"][0][field_name] = value

    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("groups", 0, field_name)


def test_shop_group_label_enforces_database_limit(
    payload: dict[str, Any],
) -> None:
    data = deepcopy(payload["shop"])
    data["groups"][0]["label"] = "x" * 50
    result = IntegrationShop.model_validate(data)
    assert result.groups[0].label == "x" * 50

    data["groups"][0]["label"] = "x" * 51
    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("groups", 0, "label")
    assert error.value.errors()[0]["type"] == "string_too_long"


def test_unknown_shop_group_fields_are_rejected(
    payload: dict[str, Any],
) -> None:
    data = deepcopy(payload["shop"])
    data["groups"][0]["unknown"] = True

    with pytest.raises(ValidationError) as error:
        IntegrationShop.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("groups", 0, "unknown")
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    "field_name",
    [
        "disableBoxDiscount",
        "disableQuantityDelivery",
        "prepaidReturns",
        "disableSaleLimit",
    ],
)
@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_operational_settings_reject_boolean_coercion(
    field_name: str,
    value: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationOperationalSettings.model_validate(
            {**payload["operationalSettings"], field_name: value}
        )

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "bool_type"


def test_shop_schema_exposes_a_closed_group_schema() -> None:
    schema = IntegrationShop.model_json_schema()

    assert schema["$defs"]["IntegrationShopGroup"]["additionalProperties"] is False
