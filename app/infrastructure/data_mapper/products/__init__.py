__all__ = ["ProductsDataMapper", "get_product", "get_products"]

from app.application.domain import Product
from app.application.ports import ProductsGateway
from app.infrastructure.data_mapper.connection import get_cursor_context

from .product import get_product as execute_get_product
from .product import get_product
from .products import get_products as execute_get_products
from .products import get_products


class ProductsDataMapper(ProductsGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        async with get_cursor_context(self._connection_string) as cur:
            return await execute_get_products(cur, limit=limit, offset=offset)

    async def get_product(self, product_id: int) -> Product:
        async with get_cursor_context(self._connection_string) as cur:
            res: Product | None = await execute_get_product(cur, product_id)
            if res is None:
                raise Exception(f"We don't have a product with {product_id} product id")
            return res
