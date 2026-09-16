import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.api.integrations.schemas.profile import (
    IntegrationAdditionalEmail,
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationPrimaryContact,
    IntegrationRegistration,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_PROFILE_MODELS: dict[str, type[BaseModel]] = {
    "credentials": IntegrationCustomerCredentials,
    "company": IntegrationCompany,
    "additionalEmail": IntegrationAdditionalEmail,
    "primaryContact": IntegrationPrimaryContact,
    "communicationPreferences": IntegrationCommunicationPreferences,
    "registration": IntegrationRegistration,
}
_NULLABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "credentials": (),
    "company": ("website", "primaryPhone", "secondaryPhone"),
    "additionalEmail": ("skype",),
    "primaryContact": ("certifiedEmail", "preferredLanguage"),
    "communicationPreferences": ("newsletter", "privacyRegistered", "rulesRegistered"),
    "registration": ("registeredAt", "verified", "lastLoginAt"),
}
_STRING_LIMITS = (
    ("credentials", "login", 50),
    ("credentials", "password", 50),
    ("company", "name", 120),
    ("company", "website", 100),
    ("company", "primaryPhone", 50),
    ("company", "secondaryPhone", 50),
    ("primaryContact", "fullName", 100),
    ("primaryContact", "email", 120),
    ("primaryContact", "certifiedEmail", 100),
    ("primaryContact", "preferredLanguage", 50),
)
_BOOLEAN_FIELDS = (
    ("additionalEmail", "commercial"),
    ("additionalEmail", "marketing"),
    ("communicationPreferences", "newsletter"),
    ("communicationPreferences", "privacyRegistered"),
    ("communicationPreferences", "rulesRegistered"),
    ("registration", "verified"),
)


@pytest.fixture
def payload() -> dict[str, Any]:
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return {**data, "additionalEmail": data["primaryContact"]["additionalEmails"][0]}


@pytest.mark.parametrize("section", _PROFILE_MODELS)
def test_profile_sections_preserve_canonical_json(
    section: str, payload: dict[str, Any]
) -> None:
    result = _PROFILE_MODELS[section].model_validate_json(json.dumps(payload[section]))

    assert result.model_dump(mode="json", by_alias=True) == payload[section]


@pytest.mark.parametrize("section", _PROFILE_MODELS)
def test_all_create_fields_are_required(section: str, payload: dict[str, Any]) -> None:
    for field_name in payload[section]:
        incomplete = {k: v for k, v in payload[section].items() if k != field_name}

        with pytest.raises(ValidationError) as error:
            _PROFILE_MODELS[section].model_validate(incomplete)

        assert [(item["loc"], item["type"]) for item in error.value.errors()] == [
            ((field_name,), "missing")
        ]


@pytest.mark.parametrize("section", _PROFILE_MODELS)
def test_only_documented_fields_accept_null(
    section: str, payload: dict[str, Any]
) -> None:
    for field_name in payload[section]:
        data = {**payload[section], field_name: None}
        if field_name in _NULLABLE_FIELDS[section]:
            result = _PROFILE_MODELS[section].model_validate(data)
            assert result.model_dump(by_alias=True)[field_name] is None
        else:
            with pytest.raises(ValidationError) as error:
                _PROFILE_MODELS[section].model_validate(data)
            assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize("section", _PROFILE_MODELS)
def test_unknown_profile_fields_are_rejected(
    section: str, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        _PROFILE_MODELS[section].model_validate({**payload[section], "unknown": True})

    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == ("unknown",)


@pytest.mark.parametrize("section", _PROFILE_MODELS)
def test_json_schema_lists_required_camel_case_fields(
    section: str, payload: dict[str, Any]
) -> None:
    schema = _PROFILE_MODELS[section].model_json_schema()

    assert set(schema["properties"]) == set(payload[section])
    assert set(schema["required"]) == set(payload[section])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(("section", "field_name", "limit"), _STRING_LIMITS)
def test_database_string_limits_accept_boundary_and_reject_overflow(
    section: str, field_name: str, limit: int, payload: dict[str, Any]
) -> None:
    model = _PROFILE_MODELS[section]
    result = model.model_validate({**payload[section], field_name: "x" * limit})
    assert result.model_dump(by_alias=True)[field_name] == "x" * limit

    with pytest.raises(ValidationError) as error:
        model.model_validate({**payload[section], field_name: "x" * (limit + 1)})

    assert error.value.errors()[0]["type"] == "string_too_long"
    assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize(("section", "field_name", "_limit"), _STRING_LIMITS)
@pytest.mark.parametrize("value", [0, False, b"text"])
def test_string_fields_reject_other_types(
    section: str, field_name: str, _limit: int, value: object, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        _PROFILE_MODELS[section].model_validate({**payload[section], field_name: value})

    assert error.value.errors()[0]["type"] == "string_type"


def test_login_trim_precedes_length_check_and_password_is_preserved() -> None:
    password = "  synthetic-password  "
    result = IntegrationCustomerCredentials.model_validate(
        {"login": "  " + "A" * 50 + "  ", "password": password}
    )

    assert result.login == "A" * 50
    assert result.password == password
    assert password not in repr(result)
    assert password not in str(result)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("login", ""), ("login", " \t\n "), ("password", "")],
)
def test_empty_credentials_are_rejected(
    field_name: str, value: str, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerCredentials.model_validate(
            {**payload["credentials"], field_name: value}
        )

    assert error.value.errors()[0]["type"] == "string_too_short"


def test_password_is_hidden_in_error_text_and_marked_write_only() -> None:
    password = "synthetic-password-" * 4
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerCredentials.model_validate(
            {"login": "acme-italia", "password": password}
        )

    assert password not in str(error.value)
    schema = IntegrationCustomerCredentials.model_json_schema()
    assert schema["properties"]["password"]["format"] == "password"
    assert schema["properties"]["password"]["writeOnly"] is True


@pytest.mark.parametrize(("section", "field_name"), _BOOLEAN_FIELDS)
@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_boolean_fields_reject_coercion(
    section: str, field_name: str, value: object, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        _PROFILE_MODELS[section].model_validate({**payload[section], field_name: value})

    assert error.value.errors()[0]["type"] == "bool_type"


def test_false_empty_strings_and_empty_email_array_are_preserved(
    payload: dict[str, Any],
) -> None:
    contact = IntegrationPrimaryContact.model_validate(
        {**payload["primaryContact"], "additionalEmails": [], "certifiedEmail": ""}
    )
    preferences = IntegrationCommunicationPreferences.model_validate(
        {"newsletter": False, "privacyRegistered": None, "rulesRegistered": True}
    )

    assert contact.additional_emails == []
    assert contact.certified_email == ""
    assert preferences.newsletter is False
    assert preferences.privacy_registered is None
    assert preferences.rules_registered is True


def test_unknown_fields_in_nested_emails_are_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationPrimaryContact.model_validate(
            {
                **payload["primaryContact"],
                "additionalEmails": [{**payload["additionalEmail"], "unknown": True}],
            }
        )

    assert error.value.errors()[0]["loc"] == ("additionalEmails", 0, "unknown")
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("field_name", ["registeredAt", "lastLoginAt"])
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
def test_registration_rejects_invalid_or_timezone_free_dates(
    field_name: str, value: object, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationRegistration.model_validate(
            {**payload["registration"], field_name: value}
        )

    assert error.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize("field_name", ["registeredAt", "lastLoginAt"])
@pytest.mark.parametrize(
    "value",
    [
        "2026-09-16T10:00:00Z",
        "2026-09-16T12:00:00.123456+02:00",
        "2026-09-16T07:00:00-03:00",
    ],
)
def test_registration_keeps_timezone_and_precision(
    field_name: str, value: str, payload: dict[str, Any]
) -> None:
    result = IntegrationRegistration.model_validate(
        {**payload["registration"], field_name: value}
    )
    timestamp = result.model_dump(by_alias=True)[field_name]
    expected = datetime.fromisoformat(value)

    assert isinstance(timestamp, datetime)
    assert timestamp == expected
    assert timestamp.utcoffset() == expected.utcoffset()
    assert timestamp.microsecond == expected.microsecond


def test_registration_ip_is_not_a_payload_field(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationRegistration.model_validate(
            {**payload["registration"], "registrationIp": "192.0.2.1"}
        )

    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == ("registrationIp",)
