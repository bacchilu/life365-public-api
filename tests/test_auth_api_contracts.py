from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app.api.auth import LoginRequest, LoginResponse
from app.api.dependencies import get_current_user
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
from app.application.exceptions import AuthenticationException


class FakeAuthService:
    def __init__(
        self,
        user: AuthenticatedUser | None = None,
        exception: AuthenticationException | None = None,
    ) -> None:
        self._user = user or _authenticated_user(
            user_id=1,
            username="admin",
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
            token_id="token-id",
        )
        self._exception = exception
        self.validated_tokens: list[str] = []

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        self.validated_tokens.append(token or "")

        if self._exception is not None:
            raise self._exception

        return self._user


def _credentials(
    token: str = "access-token",
    scheme: str = "Bearer",
) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)


def test_login_request_accepts_internal_user_principal_type() -> None:
    request = LoginRequest.model_validate(
        {
            "username": "admin",
            "password": "submitted-password",
            "principal_type": "user",
        }
    )

    assert request.username == "admin"
    assert request.password == "submitted-password"
    assert request.principal_type is PrincipalType.USER
    assert "submitted-password" not in repr(request)


def test_login_request_accepts_customer_principal_type() -> None:
    request = LoginRequest.model_validate(
        {
            "username": "customer-login",
            "password": "submitted-password",
            "principal_type": "customer",
        }
    )

    assert request.username == "customer-login"
    assert request.principal_type is PrincipalType.CUSTOMER


def test_login_request_rejects_invalid_principal_type() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {
                "username": "admin",
                "password": "submitted-password",
                "principal_type": "admin",
            }
        )


def test_login_response_exposes_token_output_without_private_fields() -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    result = LoginResult(
        user=_authenticated_user(
            user_id=1,
            username="admin",
            role=Role.ADMIN,
            principal_type=PrincipalType.USER,
            token_id="token-id",
        ),
        session=TokenSession(
            token_id="token-id",
            principal_id=1,
            principal_type=PrincipalType.USER,
            issued_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        ),
        access_token="access-token",
    )

    response = LoginResponse.from_login_result(result)
    response_data = response.model_dump()

    assert response.access_token == "access-token"
    assert response.token_type == "bearer"
    assert response.expires_at == expires_at
    assert response.user.id == 1
    assert response.user.role is Role.ADMIN
    assert "password" not in response_data
    assert "token_id" not in response_data["user"]
    assert "permissions" not in response_data["user"]
    assert "product_access" not in response_data["user"]


@pytest.mark.anyio
async def test_get_current_user_returns_validated_user() -> None:
    user = _authenticated_user(
        user_id=2,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
        token_id="token-id",
    )
    auth_service = FakeAuthService(user=user)

    result = await get_current_user(_credentials(), auth_service)

    assert result == user
    assert auth_service.validated_tokens == ["access-token"]


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


@pytest.mark.anyio
async def test_get_current_user_rejects_missing_credentials() -> None:
    auth_service = FakeAuthService()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, auth_service)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
    assert auth_service.validated_tokens == []


@pytest.mark.anyio
async def test_get_current_user_rejects_non_bearer_credentials() -> None:
    auth_service = FakeAuthService()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_credentials(scheme="Basic"), auth_service)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"
    assert auth_service.validated_tokens == []


@pytest.mark.anyio
async def test_get_current_user_maps_authentication_failures_to_401() -> None:
    auth_service = FakeAuthService(
        exception=AuthenticationException("Invalid credentials")
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_credentials(), auth_service)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
    assert auth_service.validated_tokens == ["access-token"]
