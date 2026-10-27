"""Notify Salesforce about an existing Life365 customer, synchronously."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.application.domain import AuthenticatedUser
from app.application.dtos.customer_integration.events import CustomerEventType
from app.application.exceptions import (
    CustomerNotFoundException,
    DBException,
    InvalidCustomerDataException,
    InvalidCustomerReferenceException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.customer_export_service import CustomerExportService

from .export_dependencies import get_customer_export_service, get_export_admin

router = APIRouter(tags=["integrations"])


class CustomerExportResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")
    account_id: str = Field(alias="accountId")


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or invalid Life365 bearer token"},
    403: {"description": "Admin role required"},
    404: {"description": "Life365 customer does not exist"},
    409: {"description": "Salesforce reported a conflict"},
    422: {
        "description": "Invalid ID, nonempty request body, or unrepresentable local data"
    },
    502: {"description": "Salesforce authentication, delivery, or response failed"},
    503: {"description": "Database or Salesforce configuration unavailable"},
    504: {"description": "Salesforce timeout; remote outcome may be unknown"},
}
_DESCRIPTION = (
    "Read the full existing customer from this environment's PostgreSQL database "
    "and send a complete event to Salesforce. No request body is accepted. "
    "Only admins can export customers. Both normal and /sandbox endpoints call "
    "the same real Salesforce API, currently its UAT sandbox. "
    "No customer or event state is written locally. Each request generates a new "
    "eventId. Only a rejected access token (HTTP 401) allows one reauthentication "
    "and retransmission of the identical event. No other retries or outbox exist. "
    "Send requests for a customer sequentially. A timeout may have an unknown outcome."
)


async def _export(
    reference_id: int,
    event_type: CustomerEventType,
    request: Request,
    service: CustomerExportService,
) -> CustomerExportResponse:
    if (await request.body()).strip():
        raise HTTPException(
            status_code=422,
            detail="No request body is accepted; customer data is read from the database",
        )
    try:
        result = await service.export_customer(reference_id, event_type)
    except CustomerNotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (InvalidCustomerReferenceException, InvalidCustomerDataException) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DBException:
        raise HTTPException(
            status_code=503, detail="Customer export database is unavailable"
        ) from None
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SalesforceTimeoutException as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except SalesforceRequestException as exc:
        code = 409 if exc.remote_status == 409 else 502
        raise HTTPException(status_code=code, detail=str(exc)) from None
    return CustomerExportResponse(
        success=result.success,
        eventId=result.event_id,
        referenceId=result.reference_id,
        accountId=result.account_id,
    )


@router.post(
    "/integrations/salesforce/customers/{customer_id}",
    summary="Create the Salesforce representation of a Life365 customer",
    description=_DESCRIPTION + " POST sends customer.created.",
    response_model=CustomerExportResponse,
    status_code=201,
    responses=_RESPONSES,
)
async def create_salesforce_customer(
    customer_id: Annotated[int, Path(ge=1)],
    request: Request,
    _admin: Annotated[AuthenticatedUser, Depends(get_export_admin)],
    service: Annotated[CustomerExportService, Depends(get_customer_export_service)],
) -> CustomerExportResponse:
    return await _export(customer_id, "customer.created", request, service)


@router.put(
    "/integrations/salesforce/customers/{customer_id}",
    summary="Replace the shared Salesforce customer data with current Life365 values",
    description=_DESCRIPTION
    + " PUT sends customer.updated with every shared field, including nulls and empty arrays. Life365 values take priority.",
    response_model=CustomerExportResponse,
    responses=_RESPONSES,
)
async def update_salesforce_customer(
    customer_id: Annotated[int, Path(ge=1)],
    request: Request,
    _admin: Annotated[AuthenticatedUser, Depends(get_export_admin)],
    service: Annotated[CustomerExportService, Depends(get_customer_export_service)],
) -> CustomerExportResponse:
    return await _export(customer_id, "customer.updated", request, service)
