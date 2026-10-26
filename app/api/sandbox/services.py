"""Sandbox composition: local PostgreSQL, independent sessions, no real HTTP."""

from app.application.services.auth_service import AuthService
from app.application.services.customer_service import CustomerService
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.application.services.health_service import HealthService
from app.application.services.order_service import OrderService
from app.application.services.products_service import ProductsService
from app.infrastructure.auth import PyJWTTokenCodec
from app.infrastructure.data_mapper import (
    CheckDataMapper,
    CredentialsDataMapper,
    InMemoryTokenSessionDataMapper,
    PostgreSQLCustomersDataMapper,
    PostgreSQLOrdersDataMapper,
    ProductsDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.customers import (
    PostgreSQLCustomerDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)
from app.infrastructure.disabled_portal_api import DisabledLife365PortalAPI

from .settings import SandboxSettings


class SandboxServices:
    def __init__(self, settings: SandboxSettings) -> None:
        self._settings = settings
        connection = settings.database_connection
        self.auth = AuthService(
            credentials_gateway=CredentialsDataMapper(connection),
            token_session_gateway=InMemoryTokenSessionDataMapper(),
            token_codec=PyJWTTokenCodec(
                settings.jwt_secret,
                issuer="life365-sandbox",
                audience="life365-public-api:sandbox",
            ),
        )
        self.customers = CustomerService(PostgreSQLCustomersDataMapper(connection))
        self.orders = OrderService(PostgreSQLOrdersDataMapper(connection))
        self.products = ProductsService(
            ProductsDataMapper(connection), DisabledLife365PortalAPI()
        )
        self.health = HealthService(CheckDataMapper(connection))

    def customer_synchronization(
        self, client_ip: str | None
    ) -> CustomerSynchronizationService:
        return CustomerSynchronizationService(
            PostgreSQLCustomerSynchronizationUnitOfWork(
                connection_string=self._settings.database_connection,
                fingerprint_secret=self._settings.fingerprint_secret,
                customer_mapper_factory=lambda cur: PostgreSQLCustomerDataMapper(
                    cur, registration_ip=client_ip
                ),
            )
        )
