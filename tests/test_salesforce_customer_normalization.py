"""Salesforce boolean defaults leave explicit values and original data intact."""

from copy import deepcopy
from dataclasses import fields, replace

import pytest

from app.infrastructure.salesforce.normalization import normalize_customer_data
from tests.test_customer_export_service import customer_data


@pytest.mark.parametrize(
    ("section", "name", "default"),
    [
        ("communication_preferences", "newsletter", False),
        ("communication_preferences", "privacy_registered", False),
        ("communication_preferences", "rules_registered", False),
        ("registration", "verified", False),
        ("operational_settings", "disable_quantity_delivery", False),
        ("operational_settings", "prepaid_returns", True),
        ("operational_settings", "disable_sale_limit", False),
    ],
)
@pytest.mark.parametrize("value", [None, False, True])
def test_normalization_converts_only_null_boolean_values(
    section: str, name: str, default: bool, value: bool | None
) -> None:
    original = customer_data()
    original_section = replace(getattr(original, section), **{name: value})
    original = replace(original, **{section: original_section})
    before = deepcopy(original)

    normalized = normalize_customer_data(original)

    expected = value if value is not None else default
    assert normalized == replace(
        before,
        **{section: replace(getattr(before, section), **{name: expected})},
    )
    assert normalized is not original
    assert getattr(getattr(normalized, section), name) is expected
    assert original == before
    assert getattr(original_section, name) is value
    for item in fields(original):
        if item.name not in {
            "communication_preferences",
            "registration",
            "operational_settings",
        }:
            assert getattr(normalized, item.name) is getattr(original, item.name)


def test_other_nulls_and_extension_values_are_unchanged() -> None:
    original = customer_data()
    original = replace(
        original,
        communication_preferences=replace(
            original.communication_preferences,
            newsletter=None,
            privacy_registered=None,
            rules_registered=None,
        ),
        company=replace(original.company, website=None),
        registration=replace(
            original.registration, registered_at=None, verified=None, last_login_at=None
        ),
        operational_settings=replace(
            original.operational_settings,
            disable_quantity_delivery=None,
            prepaid_returns=None,
            disable_sale_limit=None,
        ),
        extensions=replace(
            original.extensions,
            parameters={
                "privacyRegistered": None,
                "rulesRegistered": None,
                "flag": False,
                "zero": 0,
                "text": "",
                "items": [],
            },
        ),
    )
    before = deepcopy(original)

    normalized = normalize_customer_data(original)

    assert normalized.communication_preferences.newsletter is False
    assert normalized.registration.verified is False
    assert normalized.operational_settings.disable_quantity_delivery is False
    assert normalized.operational_settings.prepaid_returns is True
    assert normalized.operational_settings.disable_sale_limit is False
    assert normalized.company.website is None
    assert normalized.registration.registered_at is None
    assert normalized.registration.last_login_at is None
    assert normalized.extensions is original.extensions
    assert normalized.communication_preferences.privacy_registered is False
    assert normalized.communication_preferences.rules_registered is False
    assert original == before


def test_normalization_is_idempotent() -> None:
    original = customer_data()
    original = replace(
        original,
        communication_preferences=replace(
            original.communication_preferences,
            privacy_registered=None,
            rules_registered=None,
        ),
    )
    normalized = normalize_customer_data(original)

    assert normalize_customer_data(normalized) == normalized
