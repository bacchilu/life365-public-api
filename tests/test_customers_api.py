import os
from collections.abc import Iterator

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")

from app.api.customers import routes as customer_routes
from app.api.dependencies import get_auth_service
from app.application.domain import (
    AuthenticatedUser,
    PrincipalType,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.exceptions import AuthenticationException
from app.application.services.customer_service import CustomerService
from app.infrastructure.data_mapper import InMemoryCustomersDataMapper
from app.main import app


class FakeAuthService:
    def __init__(
        self,
        user: AuthenticatedUser | None = None,
        exception: AuthenticationException | None = None,
    ) -> None:
        self._user = user or _authenticated_user()
        self._exception = exception
        self.validated_tokens: list[str] = []

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        self.validated_tokens.append(token or "")

        if self._exception is not None:
            raise self._exception

        return self._user


@pytest.fixture(autouse=True)
def dependency_overrides(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        customer_routes,
        "customer_service",
        CustomerService(InMemoryCustomersDataMapper()),
    )
    yield
    app.dependency_overrides.clear()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


def _override_auth_service(fake_service: FakeAuthService) -> None:
    async def override() -> FakeAuthService:
        return fake_service

    app.dependency_overrides[get_auth_service] = override


def _authenticated_user(
    role: Role = Role.ADMIN,
    principal_type: PrincipalType = PrincipalType.USER,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        username=role.value,
        role=role,
        principal_type=principal_type,
        token_id="token-id",
        permissions=resolve_permissions(role),
        product_access=resolve_product_access_policy(role, user_id=1),
    )


def _assert_customer_response_shape(data: dict[str, object]) -> None:
    assert set(data) == {
        "id",
        "login",
        "email",
        "business_name",
        "business_contact_name",
        "preferred_language",
        "extra_data",
        "parameters",
        "last_login_date",
    }


@pytest.mark.anyio
async def test_list_customers_returns_paginated_customer_data() -> None:
    fake_auth_service = FakeAuthService()
    _override_auth_service(fake_auth_service)

    async with _client() as client:
        response = await client.get(
            "/customers?limit=1&offset=1",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    _assert_customer_response_shape(data[0])
    assert data[0]["id"] == 2
    assert data[0]["login"] == "second-customer"
    assert data[0]["email"] == "second.customer@example.com"
    assert "pass" not in data[0]
    assert "password" not in data[0]
    assert fake_auth_service.validated_tokens == ["access-token"]


@pytest.mark.parametrize(
    ("role", "principal_type"),
    [
        (Role.BUYER, PrincipalType.USER),
        (Role.CUSTOMER, PrincipalType.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_list_customers_allows_only_admin_role(
    role: Role,
    principal_type: PrincipalType,
) -> None:
    fake_auth_service = FakeAuthService(
        user=_authenticated_user(role=role, principal_type=principal_type)
    )
    _override_auth_service(fake_auth_service)

    async with _client() as client:
        response = await client.get(
            "/customers",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert fake_auth_service.validated_tokens == ["access-token"]


@pytest.mark.anyio
async def test_list_customers_requires_valid_bearer_token() -> None:
    fake_auth_service = FakeAuthService()
    _override_auth_service(fake_auth_service)

    async with _client() as client:
        response = await client.get("/customers")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_auth_service.validated_tokens == []


@pytest.mark.anyio
async def test_list_customers_rejects_invalid_bearer_token() -> None:
    fake_auth_service = FakeAuthService(
        exception=AuthenticationException("Invalid credentials")
    )
    _override_auth_service(fake_auth_service)

    async with _client() as client:
        response = await client.get(
            "/customers",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_auth_service.validated_tokens == ["invalid-token"]


@pytest.mark.anyio
async def test_list_customers_validates_pagination() -> None:
    fake_auth_service = FakeAuthService()
    _override_auth_service(fake_auth_service)

    async with _client() as client:
        response = await client.get(
            "/customers?limit=0&offset=-1",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_app_registers_customer_route() -> None:
    async with _client() as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "/customers" in response.json()["paths"]
