from typing import Protocol

from app.application.domain import Product


class DataGateway(Protocol):
    async def check_db(self) -> bool: ...

    async def get_products(
        self, limit: int = 100, offset: int = 0
    ) -> list[Product]: ...

    async def get_product(self, product_id: int) -> Product: ...
