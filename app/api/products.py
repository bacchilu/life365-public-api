from typing import Annotated

from fastapi import APIRouter, Query

from app.application.services.products_service import ProductDTO, ProductsService
from app.infrastructure.data_mapper import DATABASE_URL, DataMapper

router: APIRouter = APIRouter(tags=["products"])
data_mapper: DataMapper = DataMapper(DATABASE_URL)
products_service: ProductsService = ProductsService(data_mapper)


@router.get("/products")
async def get_products(
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductDTO]:
    return await products_service.get_products(limit=limit, offset=offset)
