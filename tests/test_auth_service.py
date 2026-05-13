from collections.abc import Callable
from datetime import datetime, timezone
from itertools import count

import jwt
import pytest

from app.application.domain import PrincipalIdentity, PrincipalType, Role, TokenSession
from app.application.ports import AuthenticationGateway, TokenCodec
from app.application.services.auth_service import TOKEN_EXPIRATION_DAYS, AuthService
from app.infrastructure.auth import JWT_ALGORITHM, PyJWTTokenCodec

_TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes"


class FakeAuthenticationGateway(AuthenticationGateway):
    def __init__(self) -> None:
        self.sessions: dict[str, TokenSession] = {}

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

    async def register_token_session(self, session: TokenSession) -> None:
        self.sessions[session.token_id] = session

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        return self.sessions.get(token_id)

    async def is_token_known(self, token_id: str) -> bool:
        return token_id in self.sessions

    async def is_token_revoked(self, token_id: str) -> bool:
        return False

    async def revoke_token(self, token_id: str) -> None:
        return None


def _auth_service(
    gateway: AuthenticationGateway,
    token_id_factory: Callable[[], str] = lambda: "token-id",
) -> AuthService:
    codec: TokenCodec = PyJWTTokenCodec(_TEST_SECRET_KEY)
    return AuthService(
        authentication_gateway=gateway,
        token_codec=codec,
        clock=lambda: datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        token_id_factory=token_id_factory,
    )


def _decode_token(access_token: str) -> dict[str, object]:
    return jwt.decode(
        access_token,
        _TEST_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"verify_exp": False},
    )


@pytest.mark.anyio
async def test_auth_service_issues_token_for_internal_user() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    principal = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    result = await service.issue_token(principal)
    claims = _decode_token(result.access_token)

    assert claims["sub"] == "123"
    assert isinstance(result.session.principal_id, int)
    assert claims["username"] == "buyer"
    assert claims["role"] == "buyer"
    assert claims["principal_type"] == "user"
    assert claims["jti"] == "token-id"
    assert "iat" in claims
    assert "exp" in claims
    assert result.user.id == 123
    assert result.user.role is Role.BUYER
    assert result.user.principal_type is PrincipalType.USER
    assert result.user.token_id == "token-id"
    assert result.session == gateway.sessions["token-id"]
    assert result.session.expires_at > result.session.issued_at
    assert (result.session.expires_at - result.session.issued_at).days == (
        TOKEN_EXPIRATION_DAYS
    )


@pytest.mark.anyio
async def test_auth_service_issues_token_for_customer() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    principal = PrincipalIdentity(
        id=456,
        username="customer-login",
        role=Role.CUSTOMER,
        principal_type=PrincipalType.CUSTOMER,
    )

    result = await service.issue_token(principal)
    claims = _decode_token(result.access_token)

    assert claims["sub"] == "456"
    assert claims["username"] == "customer-login"
    assert claims["role"] == "customer"
    assert claims["principal_type"] == "customer"
    assert result.user.id == 456
    assert result.user.role is Role.CUSTOMER
    assert result.user.principal_type is PrincipalType.CUSTOMER
    assert result.session.principal_type is PrincipalType.CUSTOMER


@pytest.mark.anyio
async def test_auth_service_generates_unique_token_ids() -> None:
    gateway = FakeAuthenticationGateway()
    token_ids = count(1)
    service = _auth_service(gateway, lambda: f"token-id-{next(token_ids)}")
    principal = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    first = await service.issue_token(principal)
    second = await service.issue_token(principal)

    assert first.user.token_id == "token-id-1"
    assert second.user.token_id == "token-id-2"
    assert _decode_token(first.access_token)["jti"] == "token-id-1"
    assert _decode_token(second.access_token)["jti"] == "token-id-2"
    assert set(gateway.sessions) == {"token-id-1", "token-id-2"}


@pytest.mark.anyio
async def test_auth_service_login_result_repr_does_not_expose_access_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    principal = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    result = await service.issue_token(principal)

    assert result.access_token not in repr(result)
