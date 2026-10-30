"""Salesforce normalization changes only the two approved consent flags."""

from dataclasses import fields, replace

import pytest

from app.infrastructure.salesforce.normalization import normalize_customer_data
from tests.test_customer_export_service import customer_data


@pytest.mark.parametrize("privacy", [None, False, True])
@pytest.mark.parametrize("rules", [None, False, True])
def test_normalization_converts_only_null_consent_values(
    privacy: bool | None, rules: bool | None
) -> None:
    original = customer_data()
    preferences = replace(
        original.communication_preferences,
        privacy_registered=privacy,
        rules_registered=rules,
    )
    original = replace(original, communication_preferences=preferences)

    normalized = normalize_customer_data(original)

    assert normalized is not original
    assert normalized.communication_preferences is not preferences
    assert normalized.communication_preferences.privacy_registered is (
        privacy if privacy is not None else False
    )
    assert normalized.communication_preferences.rules_registered is (
        rules if rules is not None else False
    )
    assert normalized.communication_preferences.newsletter is preferences.newsletter
    assert original.communication_preferences is preferences
    assert preferences.privacy_registered is privacy
    assert preferences.rules_registered is rules
    for item in fields(original):
        if item.name != "communication_preferences":
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
        registration=replace(original.registration, verified=None),
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

    normalized = normalize_customer_data(original)

    assert normalized.communication_preferences.newsletter is None
    assert normalized.registration.verified is None
    assert normalized.operational_settings.disable_quantity_delivery is None
    assert normalized.operational_settings.prepaid_returns is None
    assert normalized.operational_settings.disable_sale_limit is None
    assert normalized.extensions is original.extensions
    assert normalized.communication_preferences.privacy_registered is False
    assert normalized.communication_preferences.rules_registered is False
    assert original.communication_preferences.privacy_registered is None
    assert original.communication_preferences.rules_registered is None


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
