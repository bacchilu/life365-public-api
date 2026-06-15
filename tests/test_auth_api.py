import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")

import app.api.products.routes as products_routes
from app.api.dependencies import get_auth_service
from app.application.domain import (
    AllProductCreateScope,
    AllProductsScope,
    AuthenticatedUser,
    LoginResult,
    Permission,
    PrincipalType,
    ProductAccessPolicy,
    Role,
    TokenSession,
)
from app.application.dtos import ProductDTO
from app.application.exceptions import AuthenticationException, AuthorizationException
from app.main import app


class FakeAuthService:
    def __init__(
        self,
        login_result: LoginResult | None = None,
        login_exception: AuthenticationException | None = None,
        validate_user: AuthenticatedUser | None = None,
        validate_exception: AuthenticationException | None = None,
        revoke_exception: AuthenticationException | None = None,
    ) -> None:
        self._login_result = login_result or _login_result(
            username="admin",
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
        )
        self._login_exception = login_exception
        self._validate_user = validate_user or _authenticated_user(
            user_id=1,
            username="admin",
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
            token_id="token-id",
        )
        self._validate_exception = validate_exception
        self._revoke_exception = revoke_exception
        self.login_requests: list[tuple[str, str, PrincipalType]] = []
        self.validated_tokens: list[str] = []
        self.revoked_token_ids: list[str] = []

    async def login(
        self,
        username: str,
        password: str,
        principal_type: PrincipalType,
    ) -> LoginResult:
        self.login_requests.append((username, password, principal_type))

        if self._login_exception is not None:
            raise self._login_exception

        return self._login_result

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        self.validated_tokens.append(token or "")

        if self._validate_exception is not None:
            raise self._validate_exception

        return self._validate_user

    async def revoke_token(self, token_id: str) -> None:
        self.revoked_token_ids.append(token_id)

        if self._revoke_exception is not None:
            raise self._revoke_exception


class FakeProductsService:
    def __init__(
        self,
        products: list[ProductDTO] | None = None,
        product: ProductDTO | None = None,
        list_exception: AuthorizationException | None = None,
        get_exception: AuthorizationException | None = None,
    ) -> None:
        self._products = products or [_product_dto(product_id=1)]
        self._product = product or _product_dto(product_id=1)
        self._list_exception = list_exception
        self._get_exception = get_exception
        self.list_requests: list[tuple[int, int]] = []
        self.list_users: list[AuthenticatedUser] = []
        self.get_requests: list[int] = []
        self.get_users: list[AuthenticatedUser] = []

    async def get_products(
        self,
        user: AuthenticatedUser,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductDTO]:
        self.list_users.append(user)
        self.list_requests.append((limit, offset))

        if self._list_exception is not None:
            raise self._list_exception

        return self._products

    async def get_product(
        self,
        user: AuthenticatedUser,
        product_id: int,
    ) -> ProductDTO:
        self.get_users.append(user)
        self.get_requests.append(product_id)

        if self._get_exception is not None:
            raise self._get_exception

        return self._product


@pytest.fixture(autouse=True)
def dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
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


def _override_products_service(
    monkeypatch: pytest.MonkeyPatch,
    fake_service: FakeProductsService,
) -> None:
    monkeypatch.setattr(products_routes, "products_service", fake_service)


def _login_result(
    username: str,
    role: Role,
    principal_type: PrincipalType,
) -> LoginResult:
    issued_at = datetime.now(timezone.utc)
    return LoginResult(
        user=_authenticated_user(
            user_id=1,
            username=username,
            role=role,
            principal_type=principal_type,
            token_id="token-id",
        ),
        session=TokenSession(
            token_id="token-id",
            principal_id=1,
            principal_type=principal_type,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(days=30),
        ),
        access_token="access-token",
    )


def _product_dto(product_id: int) -> ProductDTO:
    return ProductDTO(
        id=product_id,
        vendor_code=f"vendor-{product_id}",
        isin=f"isin-{product_id}",
        titles={"en": f"Product {product_id}"},
        descriptions={"en": f"Description {product_id}"},
        enabled=True,
        barcodes=(f"barcode-{product_id}",),
    )


def _authenticated_user(
    user_id: int,
    username: str,
    role: Role,
    principal_type: PrincipalType,
    token_id: str,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        username=username,
        role=role,
        principal_type=principal_type,
        token_id=token_id,
        permissions=frozenset({Permission.PRODUCTS_LIST}),
        product_access=_product_access_policy(),
    )


def _product_access_policy() -> ProductAccessPolicy:
    return ProductAccessPolicy(
        create=AllProductCreateScope(),
        list=AllProductsScope(),
        read=AllProductsScope(),
        update=AllProductsScope(),
        delete=AllProductsScope(),
    )


def _assert_product_response_shape(data: dict[str, object]) -> None:
    assert set(data) == {
        "id",
        "vendor_code",
        "isin",
        "titles",
        "descriptions",
        "brand_id",
        "owner_id",
        "level_1",
        "level_2",
        "level_3",
        "enabled",
        "featured",
        "qty_box",
        "weight_gr",
        "dim_length_mm",
        "dim_width_mm",
        "dim_height_mm",
        "color",
        "certificate",
        "type1",
        "type2",
        "barcodes",
        "extra_specs",
        "keywords",
        "excluded_countries",
        "creation_date",
        "last_update",
    }


@pytest.mark.parametrize(
    ("username", "principal_type", "role"),
    [
        ("admin", "user", Role.ADMIN),
        ("buyer", "user", Role.BUYER),
        ("customer-login", "customer", Role.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_login_returns_bearer_token_for_valid_credentials(
    username: str,
    principal_type: str,
    role: Role,
) -> None:
    fake_service = FakeAuthService(
        login_result=_login_result(
            username=username,
            role=role,
            principal_type=PrincipalType(principal_type),
        )
    )
    _override_auth_service(fake_service)

    async with _client() as client:
        response = await client.post(
            "/auth/login",
            json={
                "username": username,
                "password": "submitted-password",
                "principal_type": principal_type,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "access-token"
    assert data["token_type"] == "bearer"
    assert data["user"] == {
        "id": 1,
        "username": username,
        "role": role.value,
        "principal_type": principal_type,
    }
    assert "password" not in data
    assert "token_id" not in data["user"]
    assert "permissions" not in data["user"]
    assert "product_access" not in data["user"]
    assert fake_service.login_requests == [
        (
            username,
            "submitted-password",
            PrincipalType(principal_type),
        )
    ]


@pytest.mark.anyio
async def test_login_returns_401_for_invalid_credentials() -> None:
    fake_service = FakeAuthService(
        login_exception=AuthenticationException("Invalid credentials")
    )
    _override_auth_service(fake_service)

    async with _client() as client:
        response = await client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "wrong-password",
                "principal_type": "user",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_service.login_requests == [
        ("admin", "wrong-password", PrincipalType.USER)
    ]


@pytest.mark.anyio
async def test_logout_revokes_current_token() -> None:
    fake_service = FakeAuthService()
    _override_auth_service(fake_service)

    async with _client() as client:
        response = await client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_service.validated_tokens == ["access-token"]
    assert fake_service.revoked_token_ids == ["token-id"]


@pytest.mark.anyio
async def test_logout_returns_401_for_rejected_bearer_token() -> None:
    fake_service = FakeAuthService(
        validate_exception=AuthenticationException("Invalid credentials")
    )
    _override_auth_service(fake_service)

    async with _client() as client:
        response = await client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer revoked-token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_service.validated_tokens == ["revoked-token"]
    assert fake_service.revoked_token_ids == []


@pytest.mark.anyio
async def test_logout_returns_401_when_revocation_fails() -> None:
    fake_service = FakeAuthService(
        revoke_exception=AuthenticationException("Invalid credentials")
    )
    _override_auth_service(fake_service)

    async with _client() as client:
        response = await client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_service.validated_tokens == ["access-token"]
    assert fake_service.revoked_token_ids == ["token-id"]


@pytest.mark.parametrize(
    ("user_id", "username", "role", "principal_type"),
    [
        (1, "admin", Role.ADMIN, PrincipalType.USER),
        (2, "buyer", Role.BUYER, PrincipalType.USER),
        (3, "customer-login", Role.CUSTOMER, PrincipalType.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_list_products_requires_valid_bearer_token_and_preserves_pagination(
    user_id: int,
    username: str,
    role: Role,
    principal_type: PrincipalType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticated_user = _authenticated_user(
        user_id=user_id,
        username=username,
        role=role,
        principal_type=principal_type,
        token_id=f"{role.value}-token-id",
    )
    fake_auth_service = FakeAuthService(validate_user=authenticated_user)
    fake_products_service = FakeProductsService(products=[_product_dto(product_id=101)])
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(
            "/products?limit=2&offset=5",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    data = response.json()
    _assert_product_response_shape(data[0])
    assert data[0]["id"] == 101
    assert data[0]["vendor_code"] == "vendor-101"
    assert data[0]["barcodes"] == ["barcode-101"]
    assert fake_auth_service.validated_tokens == ["access-token"]
    assert fake_products_service.list_users == [authenticated_user]
    assert fake_products_service.list_requests == [(2, 5)]
    assert fake_products_service.get_requests == []


@pytest.mark.parametrize(
    ("user_id", "username", "role", "principal_type"),
    [
        (1, "admin", Role.ADMIN, PrincipalType.USER),
        (2, "buyer", Role.BUYER, PrincipalType.USER),
        (3, "customer-login", Role.CUSTOMER, PrincipalType.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_get_product_requires_valid_bearer_token(
    user_id: int,
    username: str,
    role: Role,
    principal_type: PrincipalType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticated_user = _authenticated_user(
        user_id=user_id,
        username=username,
        role=role,
        principal_type=principal_type,
        token_id=f"{role.value}-token-id",
    )
    fake_auth_service = FakeAuthService(validate_user=authenticated_user)
    fake_products_service = FakeProductsService(product=_product_dto(product_id=42))
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(
            "/products/42",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 200
    data = response.json()
    _assert_product_response_shape(data)
    assert data["id"] == 42
    assert data["vendor_code"] == "vendor-42"
    assert data["barcodes"] == ["barcode-42"]
    assert fake_auth_service.validated_tokens == ["access-token"]
    assert fake_products_service.list_requests == []
    assert fake_products_service.get_users == [authenticated_user]
    assert fake_products_service.get_requests == [42]


@pytest.mark.anyio
async def test_list_products_returns_403_for_authorization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_auth_service = FakeAuthService()
    fake_products_service = FakeProductsService(
        list_exception=AuthorizationException(
            "Missing required permission: products:list"
        )
    )
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(
            "/products?limit=2&offset=5",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing required permission: products:list"}
    assert fake_auth_service.validated_tokens == ["access-token"]
    assert fake_products_service.list_users == [fake_auth_service._validate_user]
    assert fake_products_service.list_requests == [(2, 5)]
    assert fake_products_service.get_requests == []


@pytest.mark.anyio
async def test_get_product_returns_403_for_authorization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_auth_service = FakeAuthService()
    fake_products_service = FakeProductsService(
        get_exception=AuthorizationException("Product is outside allowed scope")
    )
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(
            "/products/42",
            headers={"Authorization": "Bearer access-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Product is outside allowed scope"}
    assert fake_auth_service.validated_tokens == ["access-token"]
    assert fake_products_service.list_requests == []
    assert fake_products_service.get_users == [fake_auth_service._validate_user]
    assert fake_products_service.get_requests == [42]


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/products", {}),
        ("/products/42", {}),
        ("/products", {"Authorization": "Basic access-token"}),
        ("/products/42", {"Authorization": "Basic access-token"}),
    ],
)
@pytest.mark.anyio
async def test_product_routes_return_401_without_valid_bearer_header(
    path: str,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_auth_service = FakeAuthService()
    fake_products_service = FakeProductsService()
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(path, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_auth_service.validated_tokens == []
    assert fake_products_service.list_requests == []
    assert fake_products_service.get_requests == []


@pytest.mark.parametrize("path", ["/products", "/products/42"])
@pytest.mark.parametrize(
    "token",
    [
        "invalid-token",
        "expired-token",
        "unknown-token",
        "revoked-token",
    ],
)
@pytest.mark.anyio
async def test_product_routes_return_401_for_rejected_bearer_tokens(
    path: str,
    token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_auth_service = FakeAuthService(
        validate_exception=AuthenticationException("Invalid credentials")
    )
    fake_products_service = FakeProductsService()
    _override_auth_service(fake_auth_service)
    _override_products_service(monkeypatch, fake_products_service)

    async with _client() as client:
        response = await client.get(
            path,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert fake_auth_service.validated_tokens == [token]
    assert fake_products_service.list_requests == []
    assert fake_products_service.get_requests == []


@pytest.mark.anyio
async def test_app_registers_auth_health_and_product_routes() -> None:
    async with _client() as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/auth/login" in paths
    assert "/auth/logout" in paths
    assert "/health" in paths
    assert "/products" in paths
    assert "/products/{product_id}" in paths
