"""Accept caller-selected products for Salesforce Marketing Flow 1."""

from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.application.domain import AuthenticatedUser
from app.application.exceptions import (
    DBException,
    OrderCrossSellNotReadyException,
    OrderNotFoundException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.order_cross_sell_service import OrderCrossSellService

from .dependencies import get_integration_user
from .order_cross_sell_dependencies import get_order_cross_sell_service

router = APIRouter(tags=["integrations"])

ReferenceId = Annotated[
    str, StringConstraints(strict=True, max_length=19, pattern=r"^[1-9][0-9]*$")
]


class OrderCrossSellBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    related_product: Annotated[list[ReferenceId], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def check_distinct_products(self) -> Self:
        if len(set(self.related_product)) != len(self.related_product):
            raise ValueError("related_product must contain three distinct product IDs")
        return self


class OrderCrossSellResponse(BaseModel):
    success: Literal[True] = True
    flow: Literal["recommended_products"] = "recommended_products"
    records_created: int = Field(alias="recordsCreated")
    record_ids: tuple[str, ...] = Field(alias="recordIds")


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or invalid Life365 bearer token"},
    403: {"description": "Integration role required; admin is not sufficient"},
    404: {"description": "Order does not exist in this Life365 environment"},
    409: {
        "description": "Order is not ready, has no valid invoice number, or has no valid customer"
    },
    422: {"description": "Invalid input"},
    502: {
        "description": "Salesforce Marketing rejected the request or returned an invalid response"
    },
    503: {"description": "Database or Salesforce configuration unavailable"},
    504: {"description": "Salesforce timeout; downstream outcome may be unknown"},
}


@router.post(
    "/integrations/salesforce/orders/{order_id}/marketing/cross-sell",
    summary="Send post-order product recommendations to Salesforce Marketing",
    description=(
        "Integration role required. The caller supplies three distinct Life365 "
        "product IDs as strings, in recommendation order. The customer ID is read "
        "from the saved order. The order must be ACCEPTED with a positive "
        "invoice_doc_n in this environment's database. "
        "This sends Flow 1 synchronously; related_product2 is not accepted. "
        "The caller decides when to send and how to prevent duplicates. "
        "This does not sync the order or change local data. Both normal and /sandbox "
        "endpoints use the configured Salesforce Marketing API."
    ),
    response_model=OrderCrossSellResponse,
    status_code=201,
    responses=_RESPONSES,
)
async def send_order_cross_sell(
    order_id: Annotated[int, Path(ge=1)],
    payload: OrderCrossSellBody,
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
    service: Annotated[OrderCrossSellService, Depends(get_order_cross_sell_service)],
) -> OrderCrossSellResponse:
    try:
        receipt = await service.send(
            order_id, tuple(int(product_id) for product_id in payload.related_product)
        )
    except OrderNotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except OrderCrossSellNotReadyException as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DBException:
        raise HTTPException(
            status_code=503, detail="Order cross-sell database is unavailable"
        ) from None
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SalesforceTimeoutException as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except SalesforceRequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return OrderCrossSellResponse(
        recordsCreated=len(receipt.record_ids), recordIds=receipt.record_ids
    )
