"""Admin-only product notifications; no product is written or deleted locally."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.application.domain import AuthenticatedUser
from app.application.dtos.product_integration import ProductEventType
from app.application.exceptions import (
    DBException,
    InvalidProductDataException,
    InvalidProductReferenceException,
    ProductNotFoundException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.product_export_service import ProductExportService

from .export_dependencies import get_export_admin
from .product_export_dependencies import get_product_export_service

router = APIRouter(tags=["integrations"])


class ProductExportResponse(BaseModel):
    success: bool
    event_id: UUID = Field(alias="eventId")
    reference_id: int = Field(alias="referenceId")
    record_id: str = Field(alias="recordId")


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or invalid Life365 bearer token"},
    403: {"description": "Admin role required"},
    404: {
        "description": "Life365 product missing, or Salesforce product missing on DELETE"
    },
    409: {"description": "Salesforce reported a conflict"},
    422: {"description": "Invalid ID, nonempty body, or unrepresentable local data"},
    502: {"description": "Salesforce authentication, delivery, or response failed"},
    503: {"description": "Database or Salesforce configuration unavailable"},
    504: {"description": "Salesforce timeout; remote outcome may be unknown"},
}
_DESCRIPTION = (
    "Read an existing product from this environment's PostgreSQL database and "
    "send one event to Salesforce. No request body is accepted. Admin role is required. "
    "referenceId is products.id, never product_stocks.id. Both normal and /sandbox "
    "endpoints call the same real Salesforce API, currently its UAT sandbox. "
    "No local product, stock, or event state is changed. Each call generates a new "
    "eventId. Only upstream HTTP 401 allows one token renewal and retransmission "
    "of the identical event. Other errors and timeouts are not retried. "
    "Send requests for a product sequentially. A timeout may have an unknown outcome. "
)


async def _export(
    product_id: int,
    event_type: ProductEventType,
    request: Request,
    service: ProductExportService,
) -> ProductExportResponse:
    if (await request.body()).strip():
        raise HTTPException(
            status_code=422,
            detail="No request body is accepted; product data is read from the database",
        )
    try:
        result = await service.export_product(product_id, event_type)
    except ProductNotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (InvalidProductDataException, InvalidProductReferenceException) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DBException:
        raise HTTPException(
            status_code=503, detail="Product export database is unavailable"
        ) from None
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SalesforceTimeoutException as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except SalesforceRequestException as exc:
        code = 502
        if exc.remote_status == 409:
            code = 409
        elif exc.remote_status == 404 and event_type == "product.deleted":
            code = 404
        raise HTTPException(status_code=code, detail=str(exc)) from None
    return ProductExportResponse(
        success=result.success,
        eventId=result.event_id,
        referenceId=result.reference_id,
        recordId=result.record_id,
    )


@router.post(
    "/integrations/salesforce/products/{product_id}",
    summary="Create the Salesforce representation of a Life365 product",
    description=_DESCRIPTION
    + "POST sends product.created with the complete minimal DTO.",
    response_model=ProductExportResponse,
    status_code=201,
    responses=_RESPONSES,
)
async def create_salesforce_product(
    product_id: Annotated[int, Path(ge=1)],
    request: Request,
    _admin: Annotated[AuthenticatedUser, Depends(get_export_admin)],
    service: Annotated[ProductExportService, Depends(get_product_export_service)],
) -> ProductExportResponse:
    return await _export(product_id, "product.created", request, service)


@router.put(
    "/integrations/salesforce/products/{product_id}",
    summary="Replace the shared Salesforce product data with current Life365 values",
    description=_DESCRIPTION
    + "PUT sends product.updated with every shared field, including nulls. Life365 values take priority. active follows products.enabled, so PUT can reactivate a remotely deactivated product.",
    response_model=ProductExportResponse,
    responses=_RESPONSES,
)
async def update_salesforce_product(
    product_id: Annotated[int, Path(ge=1)],
    request: Request,
    _admin: Annotated[AuthenticatedUser, Depends(get_export_admin)],
    service: Annotated[ProductExportService, Depends(get_product_export_service)],
) -> ProductExportResponse:
    return await _export(product_id, "product.updated", request, service)


@router.delete(
    "/integrations/salesforce/products/{product_id}",
    summary="Deactivate only the Salesforce representation of a Life365 product",
    description=_DESCRIPTION
    + "DELETE sends product.deleted without data. Salesforce sets IsActive=false and retains the record for order history. The local product only needs to exist; invalid catalog metadata does not block deactivation.",
    response_model=ProductExportResponse,
    responses=_RESPONSES,
)
async def delete_salesforce_product(
    product_id: Annotated[int, Path(ge=1)],
    request: Request,
    _admin: Annotated[AuthenticatedUser, Depends(get_export_admin)],
    service: Annotated[ProductExportService, Depends(get_product_export_service)],
) -> ProductExportResponse:
    return await _export(product_id, "product.deleted", request, service)
