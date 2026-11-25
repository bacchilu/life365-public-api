"""Compose customer reactivation with the database selected by the API."""

from app.application.services.customer_reactivation_service import (
    CustomerReactivationService,
)
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.customer_reactivation import (
    PostgreSQLCustomerReactivationDataMapper,
)
from app.infrastructure.salesforce.marketing_client import SalesforceMarketingAPI


def build_customer_reactivation_service(
    connection_string: str,
) -> CustomerReactivationService:
    return CustomerReactivationService(
        PostgreSQLCustomerReactivationDataMapper(connection_string),
        SalesforceMarketingAPI(),
    )


async def get_customer_reactivation_service() -> CustomerReactivationService:
    return build_customer_reactivation_service(DATABASE_URL)
