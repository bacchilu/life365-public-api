"""Top-level customer data for the version 1 integration contract."""

from dataclasses import dataclass

from app.application.dtos.customer_integration.address import (
    IntegrationAddress,
    IntegrationDelivery,
)
from app.application.dtos.customer_integration.commercial import IntegrationCommercial
from app.application.dtos.customer_integration.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNotes,
    IntegrationOperationalSettings,
    IntegrationShop,
)
from app.application.dtos.customer_integration.profile import (
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationPrimaryContact,
    IntegrationRegistration,
)


@dataclass(frozen=True, slots=True)
class IntegrationCustomerData:
    """Full customer payload; nullable fields still require an explicit value."""

    credentials: IntegrationCustomerCredentials
    company: IntegrationCompany
    primary_contact: IntegrationPrimaryContact
    billing_address: IntegrationAddress
    delivery: IntegrationDelivery
    tax_profile: IntegrationTaxProfile
    communication_preferences: IntegrationCommunicationPreferences
    registration: IntegrationRegistration
    commercial: IntegrationCommercial
    banking: IntegrationBanking
    shop: IntegrationShop
    operational_settings: IntegrationOperationalSettings
    notes: IntegrationCustomerNotes
    extensions: IntegrationCustomerExtensions
