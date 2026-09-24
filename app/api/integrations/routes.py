from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.api.integrations.converters.events import convert_customer_event
from app.api.integrations.schemas.events import SalesforceEventRequest
from app.application.domain import AuthenticatedUser, Role
from app.application.dtos.customer_integration.events import (
    CustomerSynchronizationResult,
)
from app.application.exceptions import (
    AuthorizationException,
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
    CustomerVersionGapException,
    DBException,
    InvalidCustomerReferenceException,
    StaleCustomerVersionException,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_store = InMemoryCustomerSynchronizationStore()


def get_customer_synchronization_service() -> CustomerSynchronizationService:
    unit_of_work = InMemoryCustomerSynchronizationUnitOfWork(
        customer_synchronization_store
    )
    return CustomerSynchronizationService(unit_of_work)


class SalesforceEventResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")


def _require_admin(user: AuthenticatedUser) -> None:
    if user.role is not Role.ADMIN:
        raise AuthorizationException("Forbidden")


@router.post(
    "/integrations/salesforce/events",
    summary="Receive a Salesforce integration event",
    description=(
        "Create or update a Life365 customer from a Salesforce event. "
        "Only an authenticated admin can send events. The current backend "
        "stores customers and processed events in memory; data is lost on "
        "restart and is not shared between workers."
    ),
    response_model=SalesforceEventResponse,
    responses={
        400: {"description": "Invalid customer reference"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Customer to update does not exist"},
        409: {"description": "Event conflict or invalid resource version"},
        422: {"description": "Invalid event payload"},
        503: {"description": "Customer persistence is unavailable"},
    },
)
async def receive_salesforce_event(
    payload: SalesforceEventRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    customer_synchronization_service: Annotated[
        CustomerSynchronizationService,
        Depends(get_customer_synchronization_service),
    ],
) -> SalesforceEventResponse:
    try:
        _require_admin(current_user)
    except AuthorizationException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    event = convert_customer_event(payload)
    try:
        result: CustomerSynchronizationResult = (
            await customer_synchronization_service.synchronize_customer(event)
        )
    except InvalidCustomerReferenceException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except CustomerNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (
        CustomerSynchronizationConflictException,
        CustomerVersionGapException,
        StaleCustomerVersionException,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except DBException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer persistence is unavailable",
        ) from exc

    return SalesforceEventResponse(
        success=result.success,
        eventId=payload.event_id,
        referenceId=result.reference_id,
    )
