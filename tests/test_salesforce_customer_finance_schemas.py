import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.api.integrations.schemas.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_MODELS: dict[str, type[BaseModel]] = {
    "taxProfile": IntegrationTaxProfile,
    "banking": IntegrationBanking,
}
_NULLABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "taxProfile": (
        "fiscalCode",
        "vatCountryCode",
        "vatNumber",
        "fiscalAgentCode",
        "secondaryTaxValue",
    ),
    "banking": ("abi", "cab", "iban"),
}
_STRING_LIMITS = (
    ("taxProfile", "fiscalCode", 20),
    ("taxProfile", "vatNumber", 20),
    ("taxProfile", "fiscalAgentCode", 45),
    ("banking", "abi", 5),
    ("banking", "cab", 5),
    ("banking", "iban", 34),
)


@pytest.fixture
def payload() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]


@pytest.mark.parametrize("section", _MODELS)
def test_finance_sections_preserve_canonical_json(
    section: str,
    payload: dict[str, Any],
) -> None:
    result = _MODELS[section].model_validate_json(json.dumps(payload[section]))

    assert result.model_dump(mode="json", by_alias=True) == payload[section]


@pytest.mark.parametrize("section", _MODELS)
def test_all_finance_create_fields_are_required(
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
def test_only_documented_finance_fields_accept_null(
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
def test_unknown_finance_fields_are_rejected(
    section: str,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        _MODELS[section].model_validate({**payload[section], "unknown": True})

    assert error.value.errors()[0]["loc"] == ("unknown",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("section", _MODELS)
def test_finance_json_schema_uses_required_contract_fields(
    section: str,
    payload: dict[str, Any],
) -> None:
    schema = _MODELS[section].model_json_schema()

    assert set(schema["properties"]) == set(payload[section])
    assert set(schema["required"]) == set(payload[section])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(("section", "field_name", "limit"), _STRING_LIMITS)
def test_finance_string_limits_accept_boundary_and_reject_overflow(
    section: str,
    field_name: str,
    limit: int,
    payload: dict[str, Any],
) -> None:
    model = _MODELS[section]
    result = model.model_validate({**payload[section], field_name: "0" * limit})
    assert result.model_dump(by_alias=True)[field_name] == "0" * limit

    with pytest.raises(ValidationError) as error:
        model.model_validate({**payload[section], field_name: "0" * (limit + 1)})

    assert error.value.errors()[0]["loc"] == (field_name,)
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize(("section", "field_name", "_limit"), _STRING_LIMITS)
@pytest.mark.parametrize("value", [0, False, b"text"])
def test_finance_string_fields_reject_other_types(
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
    ["it", "ITA", "I", "", "I1", " IT", "IT ", 12, False],
)
def test_vat_country_rejects_non_uppercase_iso_shape(
    country_code: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationTaxProfile.model_validate(
            {**payload["taxProfile"], "vatCountryCode": country_code}
        )

    assert error.value.errors()[0]["loc"] == ("vatCountryCode",)


@pytest.mark.parametrize("country_code", ["IT", "FR", "PL"])
def test_vat_country_accepts_two_uppercase_letters(
    country_code: str,
    payload: dict[str, Any],
) -> None:
    result = IntegrationTaxProfile.model_validate(
        {**payload["taxProfile"], "vatCountryCode": country_code}
    )

    assert result.vat_country_code == country_code


@pytest.mark.parametrize("value", [False, True])
def test_vies_accepts_strict_booleans(
    value: bool,
    payload: dict[str, Any],
) -> None:
    result = IntegrationTaxProfile.model_validate(
        {**payload["taxProfile"], "viesValidated": value}
    )

    assert result.vies_validated is value


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_vies_rejects_boolean_coercion(
    value: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationTaxProfile.model_validate(
            {**payload["taxProfile"], "viesValidated": value}
        )

    assert error.value.errors()[0]["type"] == "bool_type"


@pytest.mark.parametrize(
    "value",
    ["0.00", "-0.01", "9999999999999999.99", "-9999999999999999.99"],
)
def test_tax_decimal_accepts_exact_database_range(
    value: str,
    payload: dict[str, Any],
) -> None:
    result = IntegrationTaxProfile.model_validate(
        {**payload["taxProfile"], "secondaryTaxValue": value}
    )

    assert result.secondary_tax_value == value


@pytest.mark.parametrize(
    "value",
    [
        0,
        0.0,
        "0",
        "0.0",
        ".00",
        "+0.00",
        "1.234",
        "10000000000000000.00",
        "1e2",
        "NaN",
        "",
    ],
)
def test_tax_decimal_rejects_invalid_or_oversized_values(
    value: object,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationTaxProfile.model_validate(
            {**payload["taxProfile"], "secondaryTaxValue": value}
        )

    assert error.value.errors()[0]["loc"] == ("secondaryTaxValue",)


def test_tax_decimal_schema_exposes_string_pattern() -> None:
    schema = IntegrationTaxProfile.model_json_schema()
    decimal_schema = schema["properties"]["secondaryTaxValue"]["anyOf"][0]

    assert decimal_schema["type"] == "string"
    assert decimal_schema["pattern"] == r"^-?[0-9]{1,16}\.[0-9]{2}$"


@pytest.mark.parametrize(
    ("fiscal_code", "vat_number"),
    [(None, None), ("", ""), ("  ", "\t")],
)
def test_tax_profile_requires_one_nonblank_identity(
    fiscal_code: str | None,
    vat_number: str | None,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationTaxProfile.model_validate(
            {
                **payload["taxProfile"],
                "fiscalCode": fiscal_code,
                "vatNumber": vat_number,
            }
        )

    assert error.value.errors()[0]["loc"] == ()
    assert error.value.errors()[0]["type"] == "value_error"


@pytest.mark.parametrize(
    ("fiscal_code", "vat_number"),
    [("CODE", None), (None, "VAT"), ("CODE", "VAT")],
)
def test_tax_profile_accepts_each_identity_source(
    fiscal_code: str | None,
    vat_number: str | None,
    payload: dict[str, Any],
) -> None:
    result = IntegrationTaxProfile.model_validate(
        {
            **payload["taxProfile"],
            "fiscalCode": fiscal_code,
            "vatNumber": vat_number,
        }
    )

    assert result.fiscal_code == fiscal_code
    assert result.vat_number == vat_number


def test_banking_preserves_leading_zeroes() -> None:
    result = IntegrationBanking.model_validate(
        {"abi": "03069", "cab": "00001", "iban": None}
    )

    assert result.abi == "03069"
    assert result.cab == "00001"
    assert result.iban is None
