"""Apply Salesforce-specific rules without changing application customer data."""

from dataclasses import replace

from app.application.dtos.customer_integration.customer import IntegrationCustomerData


def normalize_customer_data(data: IntegrationCustomerData) -> IntegrationCustomerData:
    preferences = data.communication_preferences
    salesforce_preferences = replace(
        preferences,
        privacy_registered=(
            preferences.privacy_registered
            if preferences.privacy_registered is not None
            else False
        ),
        rules_registered=(
            preferences.rules_registered
            if preferences.rules_registered is not None
            else False
        ),
    )
    return replace(data, communication_preferences=salesforce_preferences)
