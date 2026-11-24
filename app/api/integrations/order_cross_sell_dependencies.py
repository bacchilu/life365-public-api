"""Compose cross-selling with the database selected by the API environment."""

from app.application.services.order_cross_sell_service import OrderCrossSellService
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.order_cross_sell import (
    PostgreSQLOrderCrossSellDataMapper,
)
from app.infrastructure.salesforce.marketing_client import SalesforceMarketingAPI


def build_order_cross_sell_service(connection_string: str) -> OrderCrossSellService:
    return OrderCrossSellService(
        PostgreSQLOrderCrossSellDataMapper(connection_string), SalesforceMarketingAPI()
    )


async def get_order_cross_sell_service() -> OrderCrossSellService:
    return build_order_cross_sell_service(DATABASE_URL)
