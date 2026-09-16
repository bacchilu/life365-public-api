import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.integrations.schemas.extensions import IntegrationCustomerExtensions

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


@pytest.fixture
def extensions() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]["extensions"]


def test_extensions_section_preserves_canonical_json(
    extensions: dict[str, Any],
) -> None:
    result = IntegrationCustomerExtensions.model_validate_json(json.dumps(extensions))

    assert result.model_dump(mode="json", by_alias=True) == extensions


@pytest.mark.parametrize("field_name", ["parameters", "extraData"])
def test_all_extension_create_fields_are_required(
    field_name: str,
    extensions: dict[str, Any],
) -> None:
    incomplete = {key: value for key, value in extensions.items() if key != field_name}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerExtensions.model_validate(incomplete)

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field_name", ["parameters", "extraData"])
def test_extension_fields_accept_null(
    field_name: str,
    extensions: dict[str, Any],
) -> None:
    result = IntegrationCustomerExtensions.model_validate(
        {**extensions, field_name: None}
    )

    assert result.model_dump(by_alias=True)[field_name] is None


def test_extensions_accept_arbitrary_nested_json_values(
    extensions: dict[str, Any],
) -> None:
    parameters = {
        "not_buyer": True,
        "threshold": 10,
        "ratio": 1.5,
        "label": "priority",
        "empty": None,
        "nested": {"enabled": False, "level": 2},
        "items": [1, "two", None, {"active": True}],
    }
    extra_data = {
        "origin": "salesforce",
        "annual_revenue": "100000.00",
    }

    result = IntegrationCustomerExtensions.model_validate(
        {**extensions, "parameters": parameters, "extraData": extra_data}
    )

    assert result.model_dump(mode="json", by_alias=True) == {
        "parameters": parameters,
        "extraData": extra_data,
    }


@pytest.mark.parametrize("field_name", ["parameters", "extraData"])
@pytest.mark.parametrize("value", [[], "value", 1, 1.5, True])
def test_extension_roots_require_json_objects(
    field_name: str,
    value: object,
    extensions: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerExtensions.model_validate({**extensions, field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "dict_type"


@pytest.mark.parametrize("value", [datetime(2026, 9, 16), b"bytes", {1, 2}])
def test_extensions_reject_non_json_nested_values(
    value: object,
    extensions: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerExtensions.model_validate(
            {**extensions, "parameters": {"invalid": value}}
        )

    assert error.value.errors()[0]["loc"][:2] == ("parameters", "invalid")


def test_unknown_outer_extension_fields_are_rejected(
    extensions: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerExtensions.model_validate({**extensions, "unknown": True})

    assert error.value.errors()[0]["loc"] == ("unknown",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_extension_schema_is_closed_only_at_its_outer_boundary(
    extensions: dict[str, Any],
) -> None:
    schema = IntegrationCustomerExtensions.model_json_schema()

    assert set(schema["properties"]) == set(extensions)
    assert set(schema["required"]) == set(extensions)
    assert schema["additionalProperties"] is False

    for field_name in ("parameters", "extraData"):
        object_schema = schema["properties"][field_name]["anyOf"][0]
        assert object_schema["type"] == "object"
        assert object_schema["additionalProperties"] == {"$ref": "#/$defs/JsonValue"}
