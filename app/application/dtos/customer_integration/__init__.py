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
from app.application.dtos.customer_integration.commercial import (
    IntegrationAgent,
    IntegrationCategory,
    IntegrationCommercial,
    IntegrationSalesChannel,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)
from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNote,
    IntegrationCustomerNotes,
    IntegrationOperationalSettings,
    IntegrationShop,
    IntegrationShopGroup,
)
from app.application.dtos.customer_integration.profile import (
    IntegrationAdditionalEmail,
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationPrimaryContact,
    IntegrationRegistration,
)
