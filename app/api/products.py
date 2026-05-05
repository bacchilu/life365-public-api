from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app.application.ports import DataGateway
from app.application.services.products_service import ProductDTO, ProductsService
from app.infrastructure.data_mapper import DATABASE_URL, DataMapper

router: APIRouter = APIRouter(tags=["products"])
data_mapper: DataGateway = DataMapper(DATABASE_URL)
products_service: ProductsService = ProductsService(data_mapper)


class ProductResponse(BaseModel):
    model_config = ConfigDict(title="Product")

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
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductDTO]:
    """
    Retrieve a paginated list of products.
    Use `limit` to control the number of results and `offset` to skip results.
    """
    return await products_service.get_products(limit=limit, offset=offset)


@router.get(
    "/products/{product_id}",
    summary="Get product by ID",
    response_model=ProductResponse,
)
async def get_product(product_id: Annotated[int, Path(ge=1)]) -> ProductDTO:
    """
    Retrieve a single product by its unique ID.
    The `product_id` must be a positive integer.
    """
    return await products_service.get_product(product_id)
