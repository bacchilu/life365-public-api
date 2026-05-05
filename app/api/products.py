from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.application.ports import DataGateway
from app.application.services.products_service import ProductDTO, ProductsService
from app.infrastructure.data_mapper import DATABASE_URL, DataMapper

router: APIRouter = APIRouter(tags=["products"])
data_mapper: DataGateway = DataMapper(DATABASE_URL)
products_service: ProductsService = ProductsService(data_mapper)


@router.get("/products")
async def get_products(
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductDTO]:
    return await products_service.get_products(limit=limit, offset=offset)


@router.get("/products/{product_id}")
async def get_product(product_id: Annotated[int, Path(ge=1)]) -> ProductDTO:
    return await products_service.get_product(product_id)
