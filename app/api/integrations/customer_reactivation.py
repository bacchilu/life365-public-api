"""Accept caller-selected products for Salesforce Marketing Flow 2."""

from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.application.domain import AuthenticatedUser
from app.application.dtos.customer_reactivation import CustomerReactivationRequest
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerReactivationNotReadyException,
    DBException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.customer_reactivation_service import (
    CustomerReactivationService,
)

from .customer_reactivation_dependencies import get_customer_reactivation_service
from .dependencies import get_integration_user

router = APIRouter(tags=["integrations"])

ProductId = Annotated[
    str, StringConstraints(strict=True, max_length=19, pattern=r"^[1-9][0-9]*$")
]
FourProducts = Annotated[list[ProductId], Field(min_length=4, max_length=4)]
EmptyProducts = Annotated[list[ProductId], Field(max_length=0)]


class CustomerReactivationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    related_product: FourProducts
    related_product2: FourProducts | EmptyProducts

    @model_validator(mode="after")
    def check_distinct_products(self) -> Self:
        products = self.related_product + self.related_product2
        if len(set(products)) != len(products):
            raise ValueError("Product IDs must be distinct across both lists")
        return self


class CustomerReactivationResponse(BaseModel):
    success: Literal[True] = True
    flow: Literal["cross_sell_products"] = "cross_sell_products"
    records_created: int = Field(alias="recordsCreated")
    record_ids: tuple[str, ...] = Field(alias="recordIds")


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or invalid Life365 bearer token"},
    403: {"description": "Integration role required; admin is not sufficient"},
    404: {"description": "Customer does not exist in this Life365 environment"},
    409: {"description": "Customer has no qualifying last order older than 90 days"},
    422: {"description": "Invalid customer ID or product lists"},
    502: {
        "description": "Salesforce Marketing rejected the request or returned an invalid response"
    },
    503: {"description": "Database or Salesforce configuration unavailable"},
    504: {"description": "Salesforce timeout; downstream outcome may be unknown"},
}


@router.post(
    "/integrations/salesforce/customers/{customer_id}/marketing/reactivation",
    summary="Send inactive-customer recommendations to Salesforce Marketing",
    description=(
        "Integration role required. The caller selects four Life365 product IDs for "
        "the first email and four others for the follow-up, or [] for no follow-up. "
        "Send both lists as ordered lists of strings. The customer's last order "
        "in CONFIRMED, DELIVERED, or UNDELIVERABLE must be older than 90 days. "
        "This sends Flow 2 synchronously without changing local data. The caller "
        "decides when to send. Both normal and /sandbox endpoints use the configured "
        "Salesforce Marketing API."
    ),
    response_model=CustomerReactivationResponse,
    status_code=201,
    responses=_RESPONSES,
)
async def send_customer_reactivation(
    customer_id: Annotated[int, Path(ge=1)],
    payload: CustomerReactivationBody,
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
    service: Annotated[
        CustomerReactivationService, Depends(get_customer_reactivation_service)
    ],
) -> CustomerReactivationResponse:
    request = CustomerReactivationRequest(
        customer_id=customer_id,
        product_ids=tuple(int(product_id) for product_id in payload.related_product),
        follow_up_product_ids=tuple(
            int(product_id) for product_id in payload.related_product2
        ),
    )
    try:
        receipt = await service.send(request)
    except CustomerNotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except CustomerReactivationNotReadyException as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DBException:
        raise HTTPException(
            status_code=503, detail="Customer reactivation database is unavailable"
        ) from None
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SalesforceTimeoutException as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except SalesforceRequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return CustomerReactivationResponse(
        recordsCreated=len(receipt.record_ids), recordIds=receipt.record_ids
    )
