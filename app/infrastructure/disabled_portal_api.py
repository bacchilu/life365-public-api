"""An explicit sandbox boundary: no outbound business API requests."""

from app.application.dtos import ProductRecommendation
from app.application.exceptions import ExternalIntegrationDisabledException
from app.application.ports import Life365APIGateway


class DisabledLife365PortalAPI(Life365APIGateway):
    async def recommend_products(
        self, order_id: int | None = None, customer_id: int | None = None
    ) -> list[ProductRecommendation]:
        raise ExternalIntegrationDisabledException(
            "Product recommendations are disabled in the sandbox; no external request was sent"
        )
