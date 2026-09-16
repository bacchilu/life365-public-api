import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.integrations.schemas.notes import IntegrationCustomerNotes

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_NOTE = {
    "occurredAt": "2026-09-16T10:00:00Z",
    "text": "Contact the customer about the open request.",
    "open": True,
}


@pytest.fixture
def notes() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]["notes"]


def test_notes_section_preserves_canonical_json(notes: dict[str, Any]) -> None:
    result = IntegrationCustomerNotes.model_validate_json(json.dumps(notes))

    assert result.model_dump(mode="json", by_alias=True) == notes


def test_notes_accept_a_populated_item_array(notes: dict[str, Any]) -> None:
    data = {**notes, "items": [_NOTE]}
    result = IntegrationCustomerNotes.model_validate(data)

    assert result.model_dump(mode="json", by_alias=True) == data


@pytest.mark.parametrize("field_name", ["items", "administrativeNote"])
def test_all_notes_create_fields_are_required(
    field_name: str,
    notes: dict[str, Any],
) -> None:
    incomplete = {key: value for key, value in notes.items() if key != field_name}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate(incomplete)

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "missing"


def test_only_administrative_note_accepts_null(notes: dict[str, Any]) -> None:
    result = IntegrationCustomerNotes.model_validate(
        {**notes, "administrativeNote": None}
    )
    assert result.administrative_note is None

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": None})

    assert error.value.errors()[0]["loc"] == ("items",)


def test_notes_accept_an_empty_item_array(notes: dict[str, Any]) -> None:
    result = IntegrationCustomerNotes.model_validate({**notes, "items": []})

    assert result.items == []


def test_note_items_require_a_json_array(notes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": (_NOTE,)})

    assert error.value.errors()[0]["loc"] == ("items",)
    assert error.value.errors()[0]["type"] == "list_type"


@pytest.mark.parametrize("field_name", ["occurredAt", "text", "open"])
def test_all_note_item_fields_are_required(
    field_name: str,
    notes: dict[str, Any],
) -> None:
    item = {key: value for key, value in _NOTE.items() if key != field_name}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, field_name)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("field_name", ["occurredAt", "text", "open"])
def test_note_item_fields_reject_null(
    field_name: str,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, field_name: None}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, field_name)


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-16T10:00:00Z",
        "2026-09-16T12:00:00.123456+02:00",
        "2026-09-16T07:00:00-03:00",
    ],
)
def test_note_timestamp_keeps_timezone_and_precision(
    value: str,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, "occurredAt": value}
    result = IntegrationCustomerNotes.model_validate({**notes, "items": [item]})
    timestamp = result.items[0].occurred_at
    expected = datetime.fromisoformat(value)

    assert timestamp == expected
    assert timestamp.utcoffset() == expected.utcoffset()
    assert timestamp.microsecond == expected.microsecond


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-16T10:00:00",
        "2026-09-16",
        "1787649316",
        1787649316,
        1787649316.5,
        "2026-09-16 10:00:00Z",
        "2026-02-30T10:00:00Z",
        datetime(2026, 9, 16, 10),
    ],
)
def test_note_timestamp_rejects_invalid_or_timezone_free_values(
    value: object,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, "occurredAt": value}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, "occurredAt")


@pytest.mark.parametrize("value", [False, True])
def test_note_open_accepts_strict_booleans(
    value: bool,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, "open": value}
    result = IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert result.items[0].open is value


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_note_open_rejects_boolean_coercion(
    value: object,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, "open": value}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, "open")
    assert error.value.errors()[0]["type"] == "bool_type"


@pytest.mark.parametrize("value", [0, False, b"text"])
def test_note_text_rejects_non_string_values(
    value: object,
    notes: dict[str, Any],
) -> None:
    item = {**_NOTE, "text": value}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, "text")
    assert error.value.errors()[0]["type"] == "string_type"


def test_administrative_note_enforces_database_limit(
    notes: dict[str, Any],
) -> None:
    result = IntegrationCustomerNotes.model_validate(
        {**notes, "administrativeNote": "x" * 250}
    )
    assert result.administrative_note == "x" * 250

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate(
            {**notes, "administrativeNote": "x" * 251}
        )

    assert error.value.errors()[0]["loc"] == ("administrativeNote",)
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize("field_name", ["unknown", "openCount"])
def test_unknown_and_derived_notes_fields_are_rejected(
    field_name: str,
    notes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, field_name: 0})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_unknown_note_item_fields_are_rejected(notes: dict[str, Any]) -> None:
    item = {**_NOTE, "unknown": True}

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerNotes.model_validate({**notes, "items": [item]})

    assert error.value.errors()[0]["loc"] == ("items", 0, "unknown")
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_notes_schema_exposes_the_complete_closed_contract(
    notes: dict[str, Any],
) -> None:
    schema = IntegrationCustomerNotes.model_json_schema()

    assert set(schema["properties"]) == set(notes)
    assert set(schema["required"]) == set(notes)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["IntegrationCustomerNote"]["additionalProperties"] is False
