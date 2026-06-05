from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser
from app.application.dtos import ProductDTO
from app.application.exceptions import AuthorizationException
from app.application.ports import ProductsGateway
from app.application.services.products_service import ProductsService
from app.infrastructure.data_mapper import DATABASE_URL, ProductsDataMapper

router: APIRouter = APIRouter(tags=["products"])
products_gateway: ProductsGateway = ProductsDataMapper(DATABASE_URL)
products_service: ProductsService = ProductsService(products_gateway)


def _authorization_exception(exc: AuthorizationException) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=str(exc),
    )


class ProductResponse(BaseModel):
    # model_config = ConfigDict(title="Product")

    id: int
    vendor_code: str
    isin: str

    titles: dict[str, str] = Field(default_factory=dict)
    descriptions: dict[str, str] = Field(default_factory=dict)

    brand_id: int | None = None
    owner_id: int | None = None

    level_1: int | None = None
    level_2: int | None = None
    level_3: int | None = None

    enabled: bool = False
    featured: bool = False

    qty_box: int = 1
    weight_gr: int = 0

    dim_length_mm: int | None = None
    dim_width_mm: int | None = None
    dim_height_mm: int | None = None

    color: str | None = None
    certificate: str | None = None
    type1: str | None = None
    type2: str | None = None

    barcodes: tuple[str, ...] = ()

    extra_specs: dict[str, Any] = Field(default_factory=dict)
    keywords: dict[str, Any] = Field(default_factory=dict)

    excluded_countries: tuple[int, ...] = ()

    creation_date: datetime | None = None
    last_update: int = 0


@router.get("/products", summary="List products", response_model=list[ProductResponse])
async def get_products(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductDTO]:
    """
    Retrieve a paginated list of products.
    Use `limit` to control the number of results and `offset` to skip results.
    """
    try:
        return await products_service.get_products(
            user=current_user, limit=limit, offset=offset
        )
    except AuthorizationException as exc:
        raise _authorization_exception(exc) from exc


@router.get(
    "/products/{product_id}",
    summary="Get product by ID",
    response_model=ProductResponse,
)
async def get_product(
    product_id: Annotated[int, Path(ge=1)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProductDTO:
    """
    Retrieve a single product by its unique ID.
    The `product_id` must be a positive integer.
    """
    try:
        return await products_service.get_product(
            user=current_user, product_id=product_id
        )
    except AuthorizationException as exc:
        raise _authorization_exception(exc) from exc
