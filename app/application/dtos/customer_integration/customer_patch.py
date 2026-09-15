"""Partial customer updates for the version 1 integration contract."""

from dataclasses import dataclass, fields

from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
)
from app.application.dtos.customer_integration.finance_patch import (
    IntegrationBankingPatch,
    IntegrationTaxProfilePatch,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
    IntegrationOperationalSettingsPatch,
    IntegrationShopPatch,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
    IntegrationRegistrationPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class CustomerUpdatedData:
    """Patch for a customer; UNSET leaves a section unchanged."""

    credentials: IntegrationCustomerCredentialsPatch | UnsetType = UNSET
    company: IntegrationCompanyPatch | UnsetType = UNSET
    primary_contact: IntegrationPrimaryContactPatch | UnsetType = UNSET
    billing_address: IntegrationAddressPatch | UnsetType = UNSET
    delivery: IntegrationDeliveryPatch | UnsetType = UNSET
    tax_profile: IntegrationTaxProfilePatch | UnsetType = UNSET
    communication_preferences: IntegrationCommunicationPreferencesPatch | UnsetType = (
        UNSET
    )
    registration: IntegrationRegistrationPatch | UnsetType = UNSET
    commercial: IntegrationCommercialPatch | UnsetType = UNSET
    banking: IntegrationBankingPatch | UnsetType = UNSET
    shop: IntegrationShopPatch | UnsetType = UNSET
    operational_settings: IntegrationOperationalSettingsPatch | UnsetType = UNSET
    notes: IntegrationCustomerNotesPatch | UnsetType = UNSET
    extensions: IntegrationCustomerExtensionsPatch | UnsetType = UNSET

    def __post_init__(self) -> None:
        for patch_field in fields(self):
            if getattr(self, patch_field.name) is None:
                raise ValueError(f"{patch_field.name} cannot be cleared with null")
