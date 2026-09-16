import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.integrations.schemas.events import CustomerCreatedEventRequest

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


@pytest.fixture
def event() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_complete_create_event_fixture_validates(
    event: dict[str, Any],
) -> None:
    result = CustomerCreatedEventRequest.model_validate_json(json.dumps(event))

    assert result.model_dump(mode="json", by_alias=True) == event


def test_create_event_requires_every_envelope_field(
    event: dict[str, Any],
) -> None:
    for field_name in event:
        incomplete = {key: value for key, value in event.items() if key != field_name}

        with pytest.raises(ValidationError) as error:
            CustomerCreatedEventRequest.model_validate(incomplete)

        assert error.value.errors()[0]["loc"] == (field_name,)
        assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    ("field_name", "invalid_values"),
    [
        ("schemaVersion", [0, 2, 1.0, True, "1"]),
        ("resourceVersion", [0, 2, 1.0, True, "1"]),
        ("eventType", ["customer.updated", "customer.deleted", None]),
        ("eventId", ["not-a-uuid", 1, None]),
        (
            "occurredAt",
            [
                "2026-09-03",
                "2026-09-03T12:30:00",
                1788438600,
                datetime(2026, 9, 3, 12, 30),
            ],
        ),
    ],
)
def test_create_event_rejects_invalid_envelope_values(
    field_name: str,
    invalid_values: list[object],
    event: dict[str, Any],
) -> None:
    for invalid in invalid_values:
        with pytest.raises(ValidationError) as error:
            CustomerCreatedEventRequest.model_validate(
                {**event, field_name: invalid}
            )

        assert error.value.errors()[0]["loc"] == (field_name,)


def test_create_event_does_not_accept_reference_id(
    event: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        CustomerCreatedEventRequest.model_validate({**event, "referenceId": 42})

    assert error.value.errors()[0]["loc"] == ("referenceId",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_event_rejects_unknown_data_fields(
    event: dict[str, Any],
) -> None:
    data = deepcopy(event)
    data["data"]["unknown"] = True

    with pytest.raises(ValidationError) as error:
        CustomerCreatedEventRequest.model_validate(data)

    assert error.value.errors()[0]["loc"] == ("data", "unknown")
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_create_event_schema_exposes_the_full_nested_contract(
    event: dict[str, Any],
) -> None:
    schema = CustomerCreatedEventRequest.model_json_schema()

    assert set(schema["properties"]) == set(event)
    assert set(schema["required"]) == set(event)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["eventType"]["const"] == "customer.created"
    assert schema["properties"]["data"]["$ref"] == (
        "#/$defs/IntegrationCustomerData"
    )


def test_create_event_schema_uses_strict_version_bounds() -> None:
    schema = CustomerCreatedEventRequest.model_json_schema()

    assert schema["properties"]["schemaVersion"]["type"] == "integer"
    assert schema["properties"]["schemaVersion"]["minimum"] == 1
    assert schema["properties"]["schemaVersion"]["maximum"] == 1
    assert schema["properties"]["resourceVersion"]["minimum"] == 1
    assert schema["properties"]["resourceVersion"]["maximum"] == 1
