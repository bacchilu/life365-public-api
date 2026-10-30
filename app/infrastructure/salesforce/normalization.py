"""Apply Salesforce-specific rules without changing application customer data."""

from dataclasses import replace

from app.application.dtos.customer_integration.customer import IntegrationCustomerData


def _boolean_or_default(value: bool | None, *, default: bool = False) -> bool:
    return default if value is None else value


def normalize_customer_data(data: IntegrationCustomerData) -> IntegrationCustomerData:
    preferences = data.communication_preferences
    registration = data.registration
    settings = data.operational_settings
    return replace(
        data,
        communication_preferences=replace(
            preferences,
            newsletter=_boolean_or_default(preferences.newsletter),
            privacy_registered=_boolean_or_default(preferences.privacy_registered),
            rules_registered=_boolean_or_default(preferences.rules_registered),
        ),
        registration=replace(
            registration, verified=_boolean_or_default(registration.verified)
        ),
        operational_settings=replace(
            settings,
            disable_quantity_delivery=_boolean_or_default(
                settings.disable_quantity_delivery
            ),
            prepaid_returns=_boolean_or_default(settings.prepaid_returns, default=True),
            disable_sale_limit=_boolean_or_default(settings.disable_sale_limit),
        ),
    )
