"""Authorize integration operations independently of administrative access."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser, Role


async def get_integration_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role is not Role.INTEGRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Integration role required",
        )
    return user
