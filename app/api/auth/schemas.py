from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalType,
    Role,
)


class LoginRequest(BaseModel):
    username: str
    password: str = Field(repr=False)
    principal_type: PrincipalType


class AuthenticatedUserResponse(BaseModel):
    id: int
    username: str
    role: Role
    principal_type: PrincipalType

    @classmethod
    def from_authenticated_user(
        cls,
        user: AuthenticatedUser,
    ) -> "AuthenticatedUserResponse":
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            principal_type=user.principal_type,
        )


class LoginResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: AuthenticatedUserResponse

    @classmethod
    def from_login_result(cls, result: LoginResult) -> "LoginResponse":
        return cls(
            access_token=result.access_token,
            expires_at=result.session.expires_at,
            user=AuthenticatedUserResponse.from_authenticated_user(result.user),
        )


class LogoutResponse(BaseModel):
    status: str = "ok"
