import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.integrations.schemas.commercial import IntegrationCommercial

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_NULLABLE_FIELDS = (
    "salesChannel",
    "assignedAgent",
    "paymentAgreement",
    "preferredPaymentTypeCode",
    "paymentDays",
    "paymentDaysEndOfMonth",
    "creditGranted",
    "creditValue",
)
_STRING_LIMITS = (
    ("paymentAgreement", 100),
    ("preferredPaymentTypeCode", 50),
)
_AGENT_STRING_LIMITS = (
    ("userLogin", 20),
    ("name", 30),
    ("email", 50),
    ("phone", 50),
)


@pytest.fixture
def commercial() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]["commercial"]


def test_commercial_section_preserves_canonical_json(
    commercial: dict[str, Any],
) -> None:
    result = IntegrationCommercial.model_validate_json(json.dumps(commercial))

    assert result.model_dump(mode="json", by_alias=True) == commercial


def test_all_commercial_create_fields_are_required(
    commercial: dict[str, Any],
) -> None:
    for field_name in commercial:
        incomplete = {
            key: value for key, value in commercial.items() if key != field_name
        }

        with pytest.raises(ValidationError) as error:
            IntegrationCommercial.model_validate(incomplete)

        assert error.value.errors()[0]["loc"] == (field_name,)
        assert error.value.errors()[0]["type"] == "missing"


def test_only_documented_commercial_fields_accept_null(
    commercial: dict[str, Any],
) -> None:
    for field_name in commercial:
        data = {**commercial, field_name: None}
        if field_name in _NULLABLE_FIELDS:
            result = IntegrationCommercial.model_validate(data)
            assert result.model_dump(by_alias=True)[field_name] is None
        else:
            with pytest.raises(ValidationError) as error:
                IntegrationCommercial.model_validate(data)
            assert error.value.errors()[0]["loc"] == (field_name,)


def test_empty_category_list_is_valid(commercial: dict[str, Any]) -> None:
    result = IntegrationCommercial.model_validate(
        {**commercial, "preferredCategories": []}
    )

    assert result.preferred_categories == []


def test_category_collection_requires_a_json_array(
    commercial: dict[str, Any],
) -> None:
    categories = tuple(commercial["preferredCategories"])

    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate(
            {**commercial, "preferredCategories": categories}
        )

    assert error.value.errors()[0]["loc"] == ("preferredCategories",)
    assert error.value.errors()[0]["type"] == "list_type"


@pytest.mark.parametrize(
    ("section", "field_name"),
    [
        ("preferredCategories", "code"),
        ("preferredCategories", "label"),
        ("salesChannel", "code"),
        ("salesChannel", "label"),
        ("assignedAgent", "referenceId"),
        ("assignedAgent", "userLogin"),
        ("assignedAgent", "name"),
        ("assignedAgent", "email"),
        ("assignedAgent", "phone"),
    ],
)
def test_all_nested_commercial_fields_are_required(
    section: str,
    field_name: str,
    commercial: dict[str, Any],
) -> None:
    data = deepcopy(commercial)
    nested = data[section]
    if section == "preferredCategories":
        del nested[0][field_name]
    else:
        del nested[field_name]

    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate(data)

    expected_location = (
        (section, 0, field_name)
        if section == "preferredCategories"
        else (section, field_name)
    )
    assert error.value.errors()[0]["loc"] == expected_location
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    ("section", "expected_location"),
    [
        (None, ("unknown",)),
        ("preferredCategories", ("preferredCategories", 0, "unknown")),
        ("salesChannel", ("salesChannel", "unknown")),
        ("assignedAgent", ("assignedAgent", "unknown")),
    ],
)
def test_unknown_commercial_fields_are_rejected(
    section: str | None,
    expected_location: tuple[str | int, ...],
    commercial: dict[str, Any],
) -> None:
    data = deepcopy(commercial)
    if section is None:
        data["unknown"] = True
    elif section == "preferredCategories":
        data[section][0]["unknown"] = True
    else:
        data[section]["unknown"] = True

    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate(data)

    assert error.value.errors()[0]["loc"] == expected_location
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(("field_name", "limit"), _STRING_LIMITS)
def test_commercial_string_limits_accept_boundary_and_reject_overflow(
    field_name: str,
    limit: int,
    commercial: dict[str, Any],
) -> None:
    result = IntegrationCommercial.model_validate(
        {**commercial, field_name: "x" * limit}
    )
    assert result.model_dump(by_alias=True)[field_name] == "x" * limit

    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate(
            {**commercial, field_name: "x" * (limit + 1)}
        )

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize(("field_name", "limit"), _AGENT_STRING_LIMITS)
def test_agent_string_limits_accept_boundary_and_reject_overflow(
    field_name: str,
    limit: int,
    commercial: dict[str, Any],
) -> None:
    agent = {**commercial["assignedAgent"], field_name: "x" * limit}
    result = IntegrationCommercial.model_validate(
        {**commercial, "assignedAgent": agent}
    )
    assert result.model_dump(by_alias=True)["assignedAgent"][field_name] == (
        "x" * limit
    )

    agent[field_name] = "x" * (limit + 1)
    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate({**commercial, "assignedAgent": agent})

    assert error.value.errors()[0]["loc"] == ("assignedAgent", field_name)
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize("reference_id", [0, -1, "117", 117.0, False])
def test_agent_reference_requires_a_positive_strict_integer(
    reference_id: object,
    commercial: dict[str, Any],
) -> None:
    agent = {**commercial["assignedAgent"], "referenceId": reference_id}

    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate({**commercial, "assignedAgent": agent})

    assert error.value.errors()[0]["loc"] == ("assignedAgent", "referenceId")


@pytest.mark.parametrize("field_name", ["paymentDays", "paymentDaysEndOfMonth"])
@pytest.mark.parametrize("value", ["0", 0.0, False])
def test_payment_day_fields_reject_integer_coercion(
    field_name: str,
    value: object,
    commercial: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate({**commercial, field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "int_type"


@pytest.mark.parametrize("field_name", ["paymentDays", "paymentDaysEndOfMonth"])
@pytest.mark.parametrize("value", [-1, 0, 30])
def test_payment_day_fields_preserve_database_integers(
    field_name: str,
    value: int,
    commercial: dict[str, Any],
) -> None:
    result = IntegrationCommercial.model_validate({**commercial, field_name: value})

    assert result.model_dump(by_alias=True)[field_name] == value


@pytest.mark.parametrize(
    "value",
    ["0.00", "-0.01", "99999999.99", "-99999999.99"],
)
@pytest.mark.parametrize("field_name", ["creditGranted", "creditValue"])
def test_credit_fields_accept_exact_database_range(
    field_name: str,
    value: str,
    commercial: dict[str, Any],
) -> None:
    result = IntegrationCommercial.model_validate({**commercial, field_name: value})

    assert result.model_dump(by_alias=True)[field_name] == value


@pytest.mark.parametrize(
    "value",
    [0, 0.0, "0", "0.0", ".00", "+0.00", "1.234", "100000000.00", "1e2"],
)
@pytest.mark.parametrize("field_name", ["creditGranted", "creditValue"])
def test_credit_fields_reject_invalid_or_oversized_values(
    field_name: str,
    value: object,
    commercial: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCommercial.model_validate({**commercial, field_name: value})

    assert error.value.errors()[0]["loc"] == (field_name,)


def test_commercial_schema_exposes_the_complete_closed_contract(
    commercial: dict[str, Any],
) -> None:
    schema = IntegrationCommercial.model_json_schema()

    assert set(schema["properties"]) == set(commercial)
    assert set(schema["required"]) == set(commercial)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["IntegrationAgent"]["additionalProperties"] is False
    assert schema["$defs"]["IntegrationCategory"]["additionalProperties"] is False
    assert schema["$defs"]["IntegrationSalesChannel"]["additionalProperties"] is False
