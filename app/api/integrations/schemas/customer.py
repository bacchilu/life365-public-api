"""Complete customer data for the version 1 create request."""

from pydantic import Field

from app.api.integrations.schemas.address import (
    IntegrationAddress,
    IntegrationDelivery,
)
from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.commercial import IntegrationCommercial
from app.api.integrations.schemas.extensions import IntegrationCustomerExtensions
from app.api.integrations.schemas.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)
from app.api.integrations.schemas.notes import IntegrationCustomerNotes
from app.api.integrations.schemas.profile import (
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationPrimaryContact,
    IntegrationRegistration,
)
from app.api.integrations.schemas.shop import (
    IntegrationOperationalSettings,
    IntegrationShop,
)


class IntegrationCustomerData(IntegrationRequestModel):
    credentials: IntegrationCustomerCredentials
    company: IntegrationCompany
    primary_contact: IntegrationPrimaryContact = Field(alias="primaryContact")
    billing_address: IntegrationAddress = Field(alias="billingAddress")
    delivery: IntegrationDelivery
    tax_profile: IntegrationTaxProfile = Field(alias="taxProfile")
    communication_preferences: IntegrationCommunicationPreferences = Field(
        alias="communicationPreferences"
    )
    registration: IntegrationRegistration
    commercial: IntegrationCommercial
    banking: IntegrationBanking
    shop: IntegrationShop
    operational_settings: IntegrationOperationalSettings = Field(
        alias="operationalSettings"
    )
    notes: IntegrationCustomerNotes
    extensions: IntegrationCustomerExtensions
