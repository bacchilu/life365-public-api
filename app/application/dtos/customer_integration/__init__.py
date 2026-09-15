__all__ = [
    "IntegrationAdditionalEmail",
    "IntegrationAddress",
    "IntegrationAgent",
    "IntegrationBanking",
    "IntegrationCategory",
    "IntegrationCommercial",
    "IntegrationCommunicationPreferences",
    "IntegrationCompany",
    "IntegrationCustomerCredentials",
    "IntegrationCustomerData",
    "IntegrationCustomerExtensions",
    "IntegrationCustomerNote",
    "IntegrationCustomerNotes",
    "IntegrationCustomerCredentialsPatch",
    "IntegrationCompanyPatch",
    "IntegrationPrimaryContactPatch",
    "IntegrationCommunicationPreferencesPatch",
    "IntegrationRegistrationPatch",
    "IntegrationAddressPatch",
    "IntegrationDeliveryPatch",
    "IntegrationTaxProfilePatch",
    "IntegrationBankingPatch",
    "IntegrationCommercialPatch",
    "IntegrationSalesChannelPatch",
    "IntegrationShopPatch",
    "IntegrationOperationalSettingsPatch",
    "IntegrationCustomerNotesPatch",
    "IntegrationCustomerExtensionsPatch",
    "CustomerUpdatedData",
    "UNSET",
    "UnsetType",
    "IntegrationDelivery",
    "IntegrationOperationalSettings",
    "IntegrationPrimaryContact",
    "IntegrationRegistration",
    "IntegrationSalesChannel",
    "IntegrationShop",
    "IntegrationShopGroup",
    "IntegrationTaxProfile",
]


from app.application.dtos.customer_integration.address import (
    IntegrationAddress,
    IntegrationDelivery,
)
from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.application.dtos.customer_integration.commercial import (
    IntegrationAgent,
    IntegrationCategory,
    IntegrationCommercial,
    IntegrationSalesChannel,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
    IntegrationSalesChannelPatch,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)
from app.application.dtos.customer_integration.finance_patch import (
    IntegrationBankingPatch,
    IntegrationTaxProfilePatch,
)
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNote,
    IntegrationCustomerNotes,
    IntegrationOperationalSettings,
    IntegrationShop,
    IntegrationShopGroup,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
    IntegrationOperationalSettingsPatch,
    IntegrationShopPatch,
)
from app.application.dtos.customer_integration.profile import (
    IntegrationAdditionalEmail,
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationPrimaryContact,
    IntegrationRegistration,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
    IntegrationRegistrationPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType
