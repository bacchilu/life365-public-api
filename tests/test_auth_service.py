from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count

import jwt
import pytest

from app.application.domain import (
    AllProductCreateScope,
    AllProductsScope,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductCreateScope,
    OwnerProductsScope,
    Permission,
    PrincipalIdentity,
    PrincipalType,
    ProductAccessPolicy,
    Role,
    TokenSession,
)
from app.application.exceptions import AuthenticationException
from app.application.ports import AuthenticationGateway, TokenCodec
from app.application.services.auth_service import TOKEN_EXPIRATION_DAYS, AuthService
from app.infrastructure.auth import JWT_ALGORITHM, PyJWTTokenCodec

_TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes"


class FakeAuthenticationGateway(AuthenticationGateway):
    def __init__(self) -> None:
        self.sessions: dict[str, TokenSession] = {}
        self.revoked_token_ids: set[str] = set()
        self.internal_authentication_requests: list[tuple[str, str]] = []
        self.customer_authentication_requests: list[tuple[str, str]] = []

    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        self.internal_authentication_requests.append((username, password))
        return PrincipalIdentity(
            id=1,
            username=username,
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
        )

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        self.customer_authentication_requests.append((username, password))
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
        session: TokenSession | None = self.sessions.get(token_id)
        return token_id in self.revoked_token_ids or (
            session is not None and session.revoked
        )

    async def revoke_token(self, token_id: str) -> None:
        self.revoked_token_ids.add(token_id)
        session: TokenSession | None = self.sessions.get(token_id)

        if session is not None:
            self.sessions[token_id] = replace(session, revoked=True)


def _auth_service(
    gateway: AuthenticationGateway,
    token_id_factory: Callable[[], str] = lambda: "token-id",
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> AuthService:
    codec: TokenCodec = PyJWTTokenCodec(_TEST_SECRET_KEY)
    return AuthService(
        authentication_gateway=gateway,
        token_codec=codec,
        clock=clock,
        token_id_factory=token_id_factory,
    )


def _decode_token(access_token: str) -> dict[str, object]:
    return jwt.decode(
        access_token,
        _TEST_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"verify_exp": False},
    )


def _valid_claims(
    token_id: str = "token-id",
    expires_at: datetime | None = None,
) -> dict[str, object]:
    issued_at = datetime.now(timezone.utc)
    return {
        "sub": "123",
        "username": "buyer",
        "role": "buyer",
        "principal_type": "user",
        "jti": token_id,
        "iat": issued_at,
        "exp": expires_at or issued_at + timedelta(days=30),
    }


def _encode_claims(claims: dict[str, object]) -> str:
    return PyJWTTokenCodec(_TEST_SECRET_KEY).encode(claims)


@pytest.mark.anyio
async def test_auth_service_login_authenticates_internal_user() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)

    result = await service.login(
        username="admin",
        password="submitted-password",
        principal_type=PrincipalType.USER,
    )

    assert gateway.internal_authentication_requests == [("admin", "submitted-password")]
    assert gateway.customer_authentication_requests == []
    assert result.user.username == "admin"
    assert result.user.role is Role.ADMIN
    assert result.user.principal_type is PrincipalType.USER
    assert result.user.permissions == _all_product_permissions()
    _assert_all_product_policy(result.user.product_access)
    assert result.session == gateway.sessions[result.user.token_id]


@pytest.mark.anyio
async def test_auth_service_login_authenticates_customer_and_issues_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)

    result = await service.login(
        username="customer-login",
        password="submitted-password",
        principal_type=PrincipalType.CUSTOMER,
    )

    assert gateway.internal_authentication_requests == []
    assert gateway.customer_authentication_requests == [
        ("customer-login", "submitted-password")
    ]
    assert result.user.username == "customer-login"
    assert result.user.role is Role.CUSTOMER
    assert result.user.principal_type is PrincipalType.CUSTOMER
    assert result.user.permissions == _customer_product_permissions()
    _assert_customer_product_policy(result.user.product_access)
    assert result.session == gateway.sessions[result.user.token_id]


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
    _assert_no_authorization_claims(claims)
    assert result.user.id == 123
    assert result.user.role is Role.BUYER
    assert result.user.principal_type is PrincipalType.USER
    assert result.user.token_id == "token-id"
    assert result.user.permissions == _all_product_permissions()
    _assert_buyer_product_policy(result.user.product_access, owner_id=123)
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
    _assert_no_authorization_claims(claims)
    assert result.user.id == 456
    assert result.user.role is Role.CUSTOMER
    assert result.user.principal_type is PrincipalType.CUSTOMER
    assert result.user.permissions == _customer_product_permissions()
    _assert_customer_product_policy(result.user.product_access)
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


@pytest.mark.anyio
async def test_auth_service_validates_issued_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    principal = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    result = await service.issue_token(principal)
    user = await service.validate_token(result.access_token)

    assert user == result.user
    assert user.permissions == _all_product_permissions()
    _assert_buyer_product_policy(user.product_access, owner_id=123)


@pytest.mark.anyio
@pytest.mark.parametrize("token", [None, "", "   "])
async def test_auth_service_rejects_missing_token(token: str | None) -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(token)

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_auth_service_rejects_malformed_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token("not-a-jwt")

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_auth_service_rejects_invalid_signature_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    token = PyJWTTokenCodec("different-test-secret-key-with-at-least-32-bytes").encode(
        _valid_claims()
    )

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(token)

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_auth_service_rejects_expired_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    token = _encode_claims(
        _valid_claims(
            token_id="expired-token-id",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(token)

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_auth_service_rejects_unknown_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    token = _encode_claims(_valid_claims(token_id="unknown-token-id"))

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(token)

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_auth_service_rejects_revoked_token() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    principal = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    result = await service.issue_token(principal)
    await service.revoke_token(result.user.token_id)

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(result.access_token)

    assert str(exc.value) == "Invalid credentials"
    assert gateway.sessions[result.user.token_id].revoked is True


@pytest.mark.anyio
async def test_auth_service_rejects_token_without_token_id() -> None:
    gateway = FakeAuthenticationGateway()
    service = _auth_service(gateway)
    claims = _valid_claims()
    del claims["jti"]
    token = _encode_claims(claims)

    with pytest.raises(AuthenticationException) as exc:
        await service.validate_token(token)

    assert str(exc.value) == "Invalid credentials"


def _all_product_permissions() -> frozenset[Permission]:
    return frozenset(
        {
            Permission.PRODUCTS_CREATE,
            Permission.PRODUCTS_LIST,
            Permission.PRODUCTS_READ,
            Permission.PRODUCTS_UPDATE,
            Permission.PRODUCTS_DELETE,
        }
    )


def _customer_product_permissions() -> frozenset[Permission]:
    return frozenset({Permission.PRODUCTS_LIST, Permission.PRODUCTS_READ})


def _assert_all_product_policy(policy: ProductAccessPolicy) -> None:
    assert isinstance(policy.create, AllProductCreateScope)
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, AllProductsScope)
    assert isinstance(policy.delete, AllProductsScope)


def _assert_buyer_product_policy(
    policy: ProductAccessPolicy,
    owner_id: int,
) -> None:
    assert isinstance(policy.create, OwnerProductCreateScope)
    assert policy.create.owner_id == owner_id
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, OwnerProductsScope)
    assert policy.update.owner_id == owner_id
    assert isinstance(policy.delete, OwnerProductsScope)
    assert policy.delete.owner_id == owner_id


def _assert_customer_product_policy(policy: ProductAccessPolicy) -> None:
    assert isinstance(policy.create, NoProductCreateScope)
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, NoProductsScope)
    assert isinstance(policy.delete, NoProductsScope)


def _assert_no_authorization_claims(claims: dict[str, object]) -> None:
    assert "permissions" not in claims
    assert "product_access" not in claims
