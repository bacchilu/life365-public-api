from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth.schemas import LoginRequest, LoginResponse, LogoutResponse
from app.api.dependencies import auth_exception, get_auth_service, get_current_user
from app.application.domain import AuthenticatedUser
from app.application.exceptions import AuthenticationException
from app.application.services.auth_service import AuthService

router: APIRouter = APIRouter(tags=["auth"])


@router.post("/auth/login", summary="Login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    """
    Authenticate an internal user or customer and return a Bearer access token.

    Use `principal_type` to select the identity source:

    - `user` authenticates admin and buyer accounts from the internal users
      table.
    - `customer` authenticates customer accounts from the customers table.

    On success, the response includes the JWT access token, token type,
    expiration timestamp, and authenticated user details. Passwords and stored
    credential values are never returned. Invalid credentials always return
    `401` with a generic error message.
    """
    try:
        result = await auth_service.login(
            username=request.username,
            password=request.password,
            principal_type=request.principal_type,
        )
    except AuthenticationException as exc:
        raise auth_exception() from exc

    return LoginResponse.from_login_result(result)


@router.post("/auth/logout", summary="Logout", response_model=LogoutResponse)
async def logout(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LogoutResponse:
    """
    Revoke the current Bearer token.

    The request must include a valid `Authorization: Bearer <token>` header.
    The token is validated first, then its server-side token id is marked as
    revoked so it cannot be used again. Missing, malformed, invalid, expired,
    unknown, or already unusable tokens return `401` with a generic error
    message.
    """
    try:
        await auth_service.revoke_token(current_user.token_id)
    except AuthenticationException as exc:
        raise auth_exception() from exc

    return LogoutResponse()
