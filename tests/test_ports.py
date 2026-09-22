from datetime import datetime, timedelta, timezone
from types import TracebackType
from typing import Self, cast

import pytest

from app.application.domain import (
    Customer,
    PrincipalIdentity,
    PrincipalType,
    Product,
    Role,
    TokenSession,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
)
from app.application.ports import (
    CheckGateway,
    CredentialsGateway,
    CustomerResourceVersionGateway,
    CustomerSynchronizationGateway,
    CustomerSynchronizationUnitOfWork,
    CustomersGateway,
    Life365APIGateway,
    ProcessedCustomerEventGateway,
    ProductsGateway,
    TokenSessionGateway,
)
from app.infrastructure.life365_portal_api import Life365PortalAPI


class FakeCheckGateway:
    async def check_db(self) -> bool:
        return True


class FakeProductsGateway:
    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        return [Product(id=1, vendor_code="vendor", isin="isin")]

    async def get_product(self, product_id: int) -> Product:
        return Product(id=product_id, vendor_code="vendor", isin="isin")


class FakeCustomersGateway:
    async def get_customers(
        self, limit: int = 100, offset: int = 0
    ) -> list[Customer]:
        return [Customer(id=1, login="customer", email="customer@example.com")]


class FakeCredentialsGateway(CredentialsGateway):
    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        return PrincipalIdentity(
            id=1,
            username=username,
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
        )

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        return PrincipalIdentity(
            id=2,
            username=username,
            role=Role.CUSTOMER,
            principal_type=PrincipalType.CUSTOMER,
        )


class FakeTokenSessionGateway(TokenSessionGateway):
    def __init__(self) -> None:
        self._sessions: dict[str, TokenSession] = {}
        self._revoked_tokens: set[str] = set()

    async def register_token_session(self, session: TokenSession) -> None:
        self._sessions[session.token_id] = session

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        return self._sessions.get(token_id)

    async def is_token_known(self, token_id: str) -> bool:
        return token_id in self._sessions

    async def is_token_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked_tokens

    async def revoke_token(self, token_id: str) -> None:
        self._revoked_tokens.add(token_id)


class FakeCustomerSynchronizationGateway(CustomerSynchronizationGateway):
    def __init__(self) -> None:
        self.customer_ids: set[int] = set()
        self.updated_customer_id: int | None = None

    async def customer_exists(self, reference_id: int) -> bool:
        return reference_id in self.customer_ids

    async def create_customer(self, data: IntegrationCustomerData) -> int:
        self.customer_ids.add(42)
        return 42

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None:
        self.updated_customer_id = reference_id


class FakeProcessedCustomerEventGateway(ProcessedCustomerEventGateway):
    def __init__(self) -> None:
        self.event: CustomerIntegrationEvent | None = None
        self.result: CustomerSynchronizationResult | None = None

    async def get_processed_result(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult | None:
        return self.result if event == self.event else None

    async def save_processed_result(
        self,
        event: CustomerIntegrationEvent,
        result: CustomerSynchronizationResult,
    ) -> None:
        self.event = event
        self.result = result


class FakeCustomerResourceVersionGateway(CustomerResourceVersionGateway):
    def __init__(self) -> None:
        self.versions: dict[int, int] = {}

    async def get_resource_version(self, reference_id: int) -> int | None:
        return self.versions.get(reference_id)

    async def save_resource_version(
        self, reference_id: int, resource_version: int
    ) -> None:
        self.versions[reference_id] = resource_version


class FakeCustomerSynchronizationUnitOfWork(CustomerSynchronizationUnitOfWork):
    def __init__(self) -> None:
        self.customers = FakeCustomerSynchronizationGateway()
        self.processed_events = FakeProcessedCustomerEventGateway()
        self.resource_versions = FakeCustomerResourceVersionGateway()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exception is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _as_check_gateway(gateway: CheckGateway) -> CheckGateway:
    return gateway


def _as_products_gateway(gateway: ProductsGateway) -> ProductsGateway:
    return gateway


def _as_customers_gateway(gateway: CustomersGateway) -> CustomersGateway:
    return gateway


def _as_life365_api_gateway(gateway: Life365APIGateway) -> Life365APIGateway:
    return gateway


def _as_credentials_gateway(gateway: CredentialsGateway) -> CredentialsGateway:
    return gateway


def _as_token_session_gateway(
    gateway: TokenSessionGateway,
) -> TokenSessionGateway:
    return gateway


def _as_customer_synchronization_unit_of_work(
    unit_of_work: CustomerSynchronizationUnitOfWork,
) -> CustomerSynchronizationUnitOfWork:
    return unit_of_work


@pytest.mark.anyio
async def test_credentials_gateway_contract_methods() -> None:
    gateway: CredentialsGateway = _as_credentials_gateway(FakeCredentialsGateway())

    internal_user = await gateway.authenticate_internal_user(
        username="admin",
        password="password",
    )
    customer = await gateway.authenticate_customer(
        username="customer",
        password="password",
    )

    assert internal_user.role is Role.ADMIN
    assert internal_user.principal_type is PrincipalType.USER
    assert customer.role is Role.CUSTOMER
    assert customer.principal_type is PrincipalType.CUSTOMER


@pytest.mark.anyio
async def test_token_session_gateway_contract_methods() -> None:
    gateway: TokenSessionGateway = _as_token_session_gateway(
        FakeTokenSessionGateway()
    )
    issued_at = datetime.now(timezone.utc)
    session = TokenSession(
        token_id="token-id",
        principal_id=1,
        principal_type=PrincipalType.USER,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=30),
    )

    await gateway.register_token_session(session)

    assert await gateway.get_token_session("token-id") == session
    assert await gateway.is_token_known("token-id") is True
    assert await gateway.is_token_revoked("token-id") is False

    await gateway.revoke_token("token-id")

    assert await gateway.is_token_revoked("token-id") is True


@pytest.mark.anyio
async def test_check_gateway_contract_method() -> None:
    gateway: CheckGateway = _as_check_gateway(FakeCheckGateway())

    assert await gateway.check_db() is True


@pytest.mark.anyio
async def test_products_gateway_contract_methods() -> None:
    gateway: ProductsGateway = _as_products_gateway(FakeProductsGateway())

    assert await gateway.get_products() == [
        Product(id=1, vendor_code="vendor", isin="isin")
    ]
    assert await gateway.get_product(2) == Product(
        id=2,
        vendor_code="vendor",
        isin="isin",
    )


@pytest.mark.anyio
async def test_customers_gateway_contract_method() -> None:
    gateway: CustomersGateway = _as_customers_gateway(FakeCustomersGateway())

    assert await gateway.get_customers(limit=10, offset=5) == [
        Customer(id=1, login="customer", email="customer@example.com")
    ]


def test_life365_portal_api_implements_gateway() -> None:
    gateway: Life365APIGateway = _as_life365_api_gateway(Life365PortalAPI())

    assert isinstance(gateway, Life365PortalAPI)


@pytest.mark.anyio
async def test_customer_synchronization_unit_of_work_contract() -> None:
    unit_of_work = _as_customer_synchronization_unit_of_work(
        FakeCustomerSynchronizationUnitOfWork()
    )
    customer_data = cast(IntegrationCustomerData, object())
    customer_patch = CustomerUpdatedData()
    event = cast(CustomerIntegrationEvent, object())
    result = CustomerSynchronizationResult(success=True, reference_id=42)

    async with unit_of_work:
        reference_id = await unit_of_work.customers.create_customer(customer_data)
        await unit_of_work.customers.update_customer(reference_id, customer_patch)
        await unit_of_work.resource_versions.save_resource_version(reference_id, 1)
        await unit_of_work.processed_events.save_processed_result(event, result)
        await unit_of_work.commit()

    assert await unit_of_work.customers.customer_exists(42) is True
    assert await unit_of_work.resource_versions.get_resource_version(42) == 1
    assert await unit_of_work.processed_events.get_processed_result(event) == result
    assert unit_of_work.committed is True
