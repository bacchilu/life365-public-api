import logging
import os
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    InvalidCustomerDataException,
    InvalidCustomerReferenceException,
    StaleCustomerVersionException,
)
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.customer_sync.customers import (
    PostgreSQLCustomerDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)

router: APIRouter = APIRouter(tags=["integrations"])
customer_synchronization_store = InMemoryCustomerSynchronizationStore()
logger = logging.getLogger(__name__)
load_dotenv()


class CustomerSyncBackend(StrEnum):
    MEMORY = "memory"
    POSTGRESQL = "postgresql"


CUSTOMER_SYNC_BACKEND = CustomerSyncBackend(
    os.environ.get("CUSTOMER_SYNC_BACKEND", "memory")
)


def _fingerprint_secret() -> bytes:
    load_dotenv()
    secret = os.environ.get("CUSTOMER_SYNC_FINGERPRINT_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise RuntimeError(
            "CUSTOMER_SYNC_FINGERPRINT_SECRET must contain at least 32 bytes"
        )
    return secret


async def get_customer_synchronization_service(
    request: Request,
) -> CustomerSynchronizationService:
    if CUSTOMER_SYNC_BACKEND is CustomerSyncBackend.MEMORY:
        return CustomerSynchronizationService(
            InMemoryCustomerSynchronizationUnitOfWork(customer_synchronization_store)
        )
    if CUSTOMER_SYNC_BACKEND is CustomerSyncBackend.POSTGRESQL:
        client_ip = request.client.host if request.client is not None else None
        return CustomerSynchronizationService(
            PostgreSQLCustomerSynchronizationUnitOfWork(
                connection_string=DATABASE_URL,
                fingerprint_secret=_fingerprint_secret(),
                customer_mapper_factory=lambda cur: PostgreSQLCustomerDataMapper(
                    cur, registration_ip=client_ip
                ),
            )
        )
    raise RuntimeError(f"Unsupported customer sync backend: {CUSTOMER_SYNC_BACKEND}")


class SalesforceEventResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")


def _require_admin(user: AuthenticatedUser) -> None:
    if user.role is not Role.ADMIN:
        raise AuthorizationException("Forbidden")


def _log_event(
    payload: SalesforceEventRequest, code: int, reference_id: int | None
) -> None:
    log = (
        logger.info
        if code == status.HTTP_200_OK
        else logger.error
        if code >= 500
        else logger.warning
    )
    log(
        "customer_sync event_id=%s reference_id=%s event_type=%s "
        "resource_version=%s status=%s",
        payload.event_id,
        reference_id,
        payload.event_type,
        payload.resource_version,
        code,
    )


@router.post(
    "/integrations/salesforce/events",
    summary="Receive a Salesforce integration event",
    description=(
        "Create or update a Life365 customer from a Salesforce event. "
        "Only an authenticated admin can send events. PostgreSQL mode commits "
        "the customer, event result, and resource version in one transaction. "
        "Memory mode is temporary and does not survive a restart. Repeat the "
        "same eventId with identical content to retrieve its original result. "
        "Updates require the next consecutive resourceVersion."
    ),
    response_model=SalesforceEventResponse,
    responses={
        400: {"description": "Invalid customer reference"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Customer to update does not exist"},
        409: {"description": "Event conflict or invalid resource version"},
        422: {"description": "Invalid event payload or customer data"},
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
        _log_event(
            payload,
            status.HTTP_403_FORBIDDEN,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    event = convert_customer_event(payload)
    try:
        result: CustomerSynchronizationResult = (
            await customer_synchronization_service.synchronize_customer(event)
        )
    except InvalidCustomerReferenceException as exc:
        _log_event(
            payload,
            status.HTTP_400_BAD_REQUEST,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except CustomerNotFoundException as exc:
        _log_event(
            payload,
            status.HTTP_404_NOT_FOUND,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (
        CustomerSynchronizationConflictException,
        CustomerVersionGapException,
        StaleCustomerVersionException,
    ) as exc:
        _log_event(
            payload,
            status.HTTP_409_CONFLICT,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except InvalidCustomerDataException as exc:
        _log_event(
            payload,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except DBException as exc:
        _log_event(
            payload,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            getattr(payload, "reference_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer persistence is unavailable",
        ) from exc

    _log_event(payload, status.HTTP_200_OK, result.reference_id)
    return SalesforceEventResponse(
        success=result.success,
        eventId=payload.event_id,
        referenceId=result.reference_id,
    )
