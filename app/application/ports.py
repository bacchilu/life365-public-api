from collections.abc import Mapping
from types import TracebackType
from typing import Protocol, Self

from app.application.domain import (
    Customer,
    Order,
    PrincipalIdentity,
    Product,
    TokenSession,
)
from app.application.dtos import ProductRecommendation
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
)


class CheckGateway(Protocol):
    async def check_db(self) -> bool: ...


class ProductsGateway(Protocol):
    async def get_products(
        self, limit: int = 100, offset: int = 0
    ) -> list[Product]: ...

    async def get_product(self, product_id: int) -> Product: ...


class CustomersGateway(Protocol):
    async def get_customers(
        self, limit: int = 100, offset: int = 0
    ) -> list[Customer]: ...


class CustomerSynchronizationGateway(Protocol):
    async def customer_exists(self, reference_id: int) -> bool: ...

    async def create_customer(self, data: IntegrationCustomerData) -> int: ...

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None: ...


class ProcessedCustomerEventGateway(Protocol):
    async def get_processed_result(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult | None:
        """Return the result only when the stored event content is identical."""
        ...

    async def save_processed_result(
        self,
        event: CustomerIntegrationEvent,
        result: CustomerSynchronizationResult,
    ) -> None: ...


class CustomerResourceVersionGateway(Protocol):
    async def get_resource_version(self, reference_id: int) -> int | None: ...

    async def save_resource_version(
        self, reference_id: int, resource_version: int
    ) -> None: ...


class CustomerSynchronizationUnitOfWork(Protocol):
    customers: CustomerSynchronizationGateway
    processed_events: ProcessedCustomerEventGateway
    resource_versions: CustomerResourceVersionGateway

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OrdersGateway(Protocol):
    async def get_orders(
        self, limit: int = 100, offset: int = 0
    ) -> list[Order]: ...


class Life365APIGateway(Protocol):
    async def recommend_products(
        self, order_id: int | None = None, customer_id: int | None = None
    ) -> list[ProductRecommendation]: ...


class CredentialsGateway(Protocol):
    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity: ...

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity: ...


class TokenSessionGateway(Protocol):
    async def register_token_session(self, session: TokenSession) -> None: ...

    async def get_token_session(self, token_id: str) -> TokenSession | None: ...

    async def is_token_known(self, token_id: str) -> bool: ...

    async def is_token_revoked(self, token_id: str) -> bool: ...

    async def revoke_token(self, token_id: str) -> None: ...


class TokenCodec(Protocol):
    def encode(self, claims: Mapping[str, object]) -> str: ...

    def decode(self, token: str) -> Mapping[str, object]: ...
