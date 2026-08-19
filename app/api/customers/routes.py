from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser, Customer, Role
from app.application.exceptions import AuthorizationException
from app.application.ports import CustomersGateway
from app.application.services.customer_service import CustomerService
from app.infrastructure.data_mapper import CustomersDataMapper

router: APIRouter = APIRouter(tags=["customers"])
customers_gateway: CustomersGateway = CustomersDataMapper()
customer_service: CustomerService = CustomerService(customers_gateway)


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


def _customer_to_response(customer: Customer) -> CustomerResponse:
    return CustomerResponse(
        id=customer.id,
        login=customer.login,
        email=customer.email,
        business_name=customer.business_name,
        business_contact_name=customer.business_contact_name,
        preferred_language=customer.preferred_language,
        extra_data=customer.extra_data,
        parameters=customer.parameters,
        last_login_date=customer.last_login_date,
    )


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

    customers: list[Customer] = await customer_service.get_customers(
        limit=limit,
        offset=offset,
    )
    return [_customer_to_response(customer) for customer in customers]
