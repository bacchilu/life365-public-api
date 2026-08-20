import os
from collections.abc import Iterator

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")

from app.api.dependencies import get_auth_service
from app.api.orders import routes as order_routes
from app.application.domain import (
    AuthenticatedUser,
    PrincipalType,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.services.order_service import OrderService
from app.infrastructure.data_mapper import InMemoryOrdersDataMapper
from app.main import app


class FakeAuthService:
    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=1,
            username="admin",
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
            token_id="token-id",
            permissions=resolve_permissions(Role.ADMIN),
            product_access=resolve_product_access_policy(Role.ADMIN, user_id=1),
        )


@pytest.fixture(autouse=True)
def dependency_overrides(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        order_routes,
        "order_service",
        OrderService(InMemoryOrdersDataMapper()),
    )
    yield
    app.dependency_overrides.clear()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.anyio
async def test_list_orders_returns_paginated_final_orders() -> None:
    fake_auth_service = FakeAuthService()

    async def override_auth_service() -> FakeAuthService:
        return fake_auth_service

    app.dependency_overrides[get_auth_service] = override_auth_service

    async with _client() as client:
        response = await client.get(
            "/orders?limit=1&offset=1",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1002,
            "customer_id": 202,
            "order_date": "2026-08-02T09:15:00Z",
            "logistic_state": "DELIVERED",
            "financial_state": "UNPAID",
            "total": "25.00",
            "customer_reference": None,
            "details": [
                {
                    "id": 5002,
                    "product_id": 102,
                    "product_stock_id": 10002,
                    "isin": "TEST-PRODUCT-002",
                    "description": "Second example product",
                    "quantity": 1,
                    "unit_price": "25.00",
                }
            ],
        }
    ]


@pytest.mark.anyio
async def test_list_orders_requires_authentication() -> None:
    async with _client() as client:
        response = await client.get("/orders")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


@pytest.mark.anyio
async def test_list_orders_validates_pagination() -> None:
    fake_auth_service = FakeAuthService()

    async def override_auth_service() -> FakeAuthService:
        return fake_auth_service

    app.dependency_overrides[get_auth_service] = override_auth_service

    async with _client() as client:
        response = await client.get(
            "/orders?limit=0&offset=-1",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 422
