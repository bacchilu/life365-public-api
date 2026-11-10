"""Integration-only synchronous order exports; never write the Life365 order."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.application.domain import AuthenticatedUser
from app.application.dtos.order_integration import OrderEventType
from app.application.exceptions import (
    DBException,
    InvalidOrderDataException,
    InvalidOrderReferenceException,
    OrderNotFoundException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.order_export_service import OrderExportService

from .dependencies import get_integration_user
from .order_export_dependencies import get_order_export_service

router = APIRouter(tags=["integrations"])


class OrderExportResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")
    record_id: str = Field(alias="recordId")


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or invalid Life365 bearer token"},
    403: {"description": "Integration role required; admin is not sufficient"},
    404: {
        "description": "Local order missing, Salesforce customer not synchronized, or remote order missing on DELETE"
    },
    409: {"description": "Salesforce reported a conflict"},
    422: {
        "description": "Invalid ID, nonempty body, or order data/references not representable"
    },
    502: {"description": "Salesforce authentication, delivery, or response failed"},
    503: {"description": "Database or Salesforce configuration unavailable"},
    504: {"description": "Salesforce timeout; remote outcome may be unknown"},
}
_DESCRIPTION = (
    "Read an existing order from this environment's PostgreSQL database and send one "
    "event to Salesforce. Integration role required; admins are not authorized. No request body is accepted. "
    "referenceId is orders.id; lines use products.id, not stock IDs. "
    "Both normal and /sandbox endpoints call the same real Salesforce API, currently UAT. "
    "The customer must already exist in Salesforce; missing products may be created "
    "there as placeholders. No local order or event history is changed. "
    "status is the unchanged logistic state; no date/state filter is applied. "
    "Discounts keep negative lineTotal with nonnegative unitPrice. Shipping uses "
    "one ADMGST product from the selected database. net includes signed lines and "
    "shipping; gross is the stored total; tax is their difference, not a recomputed VAT rate. "
    "Header stamp duty is unsupported. Each call generates a new eventId. Only a "
    "remote HTTP 401 permits one token renewal and retry of the identical event. "
    "Other failures are not retried; send requests for each order sequentially. "
)


async def _export(
    order_id: int,
    event_type: OrderEventType,
    request: Request,
    service: OrderExportService,
) -> OrderExportResponse:
    if (await request.body()).strip():
        raise HTTPException(
            status_code=422,
            detail="No request body is accepted; order data is read from the database",
        )
    try:
        result = await service.export_order(order_id, event_type)
    except OrderNotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (InvalidOrderReferenceException, InvalidOrderDataException) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DBException:
        raise HTTPException(
            status_code=503, detail="Order export database is unavailable"
        ) from None
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SalesforceTimeoutException as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except SalesforceRequestException as exc:
        code = (
            404
            if exc.remote_status == 404
            else 409
            if exc.remote_status == 409
            else 502
        )
        raise HTTPException(status_code=code, detail=str(exc)) from None
    return OrderExportResponse(
        success=result.success,
        eventId=result.event_id,
        referenceId=result.reference_id,
        recordId=result.record_id,
    )


@router.post(
    "/integrations/salesforce/orders/{order_id}",
    summary="Create the Salesforce representation of a Life365 order",
    description=_DESCRIPTION
    + "POST sends order.created with the complete minimal DTO.",
    response_model=OrderExportResponse,
    status_code=201,
    responses=_RESPONSES,
)
async def create_salesforce_order(
    order_id: Annotated[int, Path(ge=1)],
    request: Request,
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
    service: Annotated[OrderExportService, Depends(get_order_export_service)],
) -> OrderExportResponse:
    return await _export(order_id, "order.created", request, service)


@router.put(
    "/integrations/salesforce/orders/{order_id}",
    summary="Replace the shared Salesforce order data with current Life365 values",
    description=_DESCRIPTION
    + "PUT sends order.updated with the complete snapshot and all lines; supplied lines replace remote lines. Life365 values take priority.",
    response_model=OrderExportResponse,
    responses=_RESPONSES,
)
async def update_salesforce_order(
    order_id: Annotated[int, Path(ge=1)],
    request: Request,
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
    service: Annotated[OrderExportService, Depends(get_order_export_service)],
) -> OrderExportResponse:
    return await _export(order_id, "order.updated", request, service)


@router.delete(
    "/integrations/salesforce/orders/{order_id}",
    summary="Mark only the Salesforce order as deleted and preserve its history",
    description=_DESCRIPTION
    + "DELETE checks local existence only and sends order.deleted without data. Salesforce marks its integration status deleted; it does not physically remove the order. The Life365 order and logistic state are unchanged.",
    response_model=OrderExportResponse,
    responses=_RESPONSES,
)
async def delete_salesforce_order(
    order_id: Annotated[int, Path(ge=1)],
    request: Request,
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
    service: Annotated[OrderExportService, Depends(get_order_export_service)],
) -> OrderExportResponse:
    return await _export(order_id, "order.deleted", request, service)
