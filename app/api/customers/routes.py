from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser, Role
from app.application.exceptions import AuthorizationException

router: APIRouter = APIRouter(tags=["customers"])


class CustomerResponse(BaseModel):
    id: int
    login: str
    email: str
    business_name: str | None = None
    business_contact_name: str | None = None
    preferred_language: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    last_login_date: datetime | None = None


def _require_admin(user: AuthenticatedUser) -> None:
    if user.role is not Role.ADMIN:
        raise AuthorizationException("Forbidden")


@router.get(
    "/customers",
    summary="List customers",
    response_model=list[CustomerResponse],
)
async def get_customers(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CustomerResponse]:
    """
    Retrieve a paginated list of customers.

    This endpoint currently returns fixed placeholder data. The application
    service and data mapper implementation will replace this stub later.
    """
    try:
        _require_admin(current_user)
    except AuthorizationException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    return [
        CustomerResponse(
            id=1,
            login="customer-login",
            email="customer@example.com",
            business_name="Example Business",
            business_contact_name="Example Contact",
            preferred_language="it",
        ),
        CustomerResponse(
            id=2,
            login="second-customer",
            email="second.customer@example.com",
            business_name="Second Business",
            business_contact_name="Second Contact",
            preferred_language="en",
        ),
    ]
