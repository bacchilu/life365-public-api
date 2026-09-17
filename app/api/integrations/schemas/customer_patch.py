"""Complete customer patch for version 1 update requests."""

from pydantic import Field

from app.api.integrations.schemas.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.commercial_patch import IntegrationCommercialPatch
from app.api.integrations.schemas.finance_patch import (
    IntegrationBankingPatch,
    IntegrationTaxProfilePatch,
)
from app.api.integrations.schemas.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
    IntegrationOperationalSettingsPatch,
    IntegrationShopPatch,
)
from app.api.integrations.schemas.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
    IntegrationRegistrationPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


class CustomerUpdatedData(IntegrationRequestModel):
    credentials: IntegrationCustomerCredentialsPatch | UnsetType = UNSET
    company: IntegrationCompanyPatch | UnsetType = UNSET
    primary_contact: IntegrationPrimaryContactPatch | UnsetType = Field(
        default=UNSET, alias="primaryContact"
    )
    billing_address: IntegrationAddressPatch | UnsetType = Field(
        default=UNSET, alias="billingAddress"
    )
    delivery: IntegrationDeliveryPatch | UnsetType = UNSET
    tax_profile: IntegrationTaxProfilePatch | UnsetType = Field(
        default=UNSET, alias="taxProfile"
    )
    communication_preferences: IntegrationCommunicationPreferencesPatch | UnsetType = (
        Field(default=UNSET, alias="communicationPreferences")
    )
    registration: IntegrationRegistrationPatch | UnsetType = UNSET
    commercial: IntegrationCommercialPatch | UnsetType = UNSET
    banking: IntegrationBankingPatch | UnsetType = UNSET
    shop: IntegrationShopPatch | UnsetType = UNSET
    operational_settings: IntegrationOperationalSettingsPatch | UnsetType = Field(
        default=UNSET, alias="operationalSettings"
    )
    notes: IntegrationCustomerNotesPatch | UnsetType = UNSET
    extensions: IntegrationCustomerExtensionsPatch | UnsetType = UNSET
