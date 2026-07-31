from datetime import datetime, timedelta, timezone

import pytest

from app.application.domain import (
    PrincipalIdentity,
    PrincipalType,
    Product,
    Role,
    TokenSession,
)
from app.application.ports import (
    CheckGateway,
    CredentialsGateway,
    Life365APIGateway,
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


def _as_check_gateway(gateway: CheckGateway) -> CheckGateway:
    return gateway


def _as_products_gateway(gateway: ProductsGateway) -> ProductsGateway:
    return gateway


def _as_life365_api_gateway(gateway: Life365APIGateway) -> Life365APIGateway:
    return gateway


def _as_credentials_gateway(gateway: CredentialsGateway) -> CredentialsGateway:
    return gateway


def _as_token_session_gateway(
    gateway: TokenSessionGateway,
) -> TokenSessionGateway:
    return gateway


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


def test_life365_portal_api_implements_gateway() -> None:
    gateway: Life365APIGateway = _as_life365_api_gateway(Life365PortalAPI())

    assert isinstance(gateway, Life365PortalAPI)
