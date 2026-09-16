import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.integrations.schemas.customer import IntegrationCustomerData

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_EXPECTED_SECTIONS = {
    "credentials",
    "company",
    "primaryContact",
    "billingAddress",
    "delivery",
    "taxProfile",
    "communicationPreferences",
    "registration",
    "commercial",
    "banking",
    "shop",
    "operationalSettings",
    "notes",
    "extensions",
}
_EXPECTED_NESTED_SCHEMAS = {
    "IntegrationAdditionalEmail",
    "IntegrationAddress",
    "IntegrationAgent",
    "IntegrationBanking",
    "IntegrationCategory",
    "IntegrationCommercial",
    "IntegrationCommunicationPreferences",
    "IntegrationCompany",
    "IntegrationCustomerCredentials",
    "IntegrationCustomerExtensions",
    "IntegrationCustomerNote",
    "IntegrationCustomerNotes",
    "IntegrationDelivery",
    "IntegrationOperationalSettings",
    "IntegrationPrimaryContact",
    "IntegrationRegistration",
    "IntegrationSalesChannel",
    "IntegrationShop",
    "IntegrationShopGroup",
    "IntegrationTaxProfile",
}


@pytest.fixture
def customer_data() -> dict[str, Any]:
    document = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return document["data"]


def test_complete_customer_create_fixture_validates(
    customer_data: dict[str, Any],
) -> None:
    result = IntegrationCustomerData.model_validate_json(
        json.dumps(customer_data)
    )

    assert result.model_dump(mode="json", by_alias=True) == customer_data


def test_every_customer_create_section_is_required(
    customer_data: dict[str, Any],
) -> None:
    for section in customer_data:
        incomplete = {
            key: value for key, value in customer_data.items() if key != section
        }

        with pytest.raises(ValidationError) as error:
            IntegrationCustomerData.model_validate(incomplete)

        assert error.value.errors()[0]["loc"] == (section,)
        assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("section", sorted(_EXPECTED_SECTIONS))
def test_customer_create_sections_reject_null(
    section: str,
    customer_data: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerData.model_validate(
            {**customer_data, section: None}
        )

    assert error.value.errors()[0]["loc"] == (section,)


def test_unknown_customer_create_sections_are_rejected(
    customer_data: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as error:
        IntegrationCustomerData.model_validate(
            {**customer_data, "unknown": {}}
        )

    assert error.value.errors()[0]["loc"] == ("unknown",)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_nested_validation_error_keeps_the_complete_json_path(
    customer_data: dict[str, Any],
) -> None:
    invalid = deepcopy(customer_data)
    del invalid["commercial"]["assignedAgent"]["referenceId"]

    with pytest.raises(ValidationError) as error:
        IntegrationCustomerData.model_validate(invalid)

    assert error.value.errors()[0]["loc"] == (
        "commercial",
        "assignedAgent",
        "referenceId",
    )
    assert error.value.errors()[0]["type"] == "missing"


def test_customer_create_representation_hides_password(
    customer_data: dict[str, Any],
) -> None:
    result = IntegrationCustomerData.model_validate(customer_data)

    assert customer_data["credentials"]["password"] not in repr(result)


def test_customer_create_schema_exposes_all_sections_and_nested_models(
    customer_data: dict[str, Any],
) -> None:
    schema = IntegrationCustomerData.model_json_schema()

    assert set(schema["properties"]) == _EXPECTED_SECTIONS
    assert set(schema["properties"]) == set(customer_data)
    assert set(schema["required"]) == _EXPECTED_SECTIONS
    assert schema["additionalProperties"] is False
    assert _EXPECTED_NESTED_SCHEMAS <= set(schema["$defs"])


def test_customer_create_schema_marks_password_as_write_only() -> None:
    schema = IntegrationCustomerData.model_json_schema()
    password_schema = schema["$defs"]["IntegrationCustomerCredentials"][
        "properties"
    ]["password"]

    assert password_schema["format"] == "password"
    assert password_schema["writeOnly"] is True
