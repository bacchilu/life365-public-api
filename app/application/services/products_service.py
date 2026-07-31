from app.application.domain import (
    AuthenticatedUser,
    AuthorizationService,
    Permission,
    Product,
)
from app.application.dtos import ProductDTO, product_to_dto
from app.application.exceptions import AuthorizationException, DBException
from app.application.ports import Life365APIGateway, ProductsGateway


class ProductsService:
    def __init__(
        self,
        data_mapper: ProductsGateway,
        life365_api_gateway: Life365APIGateway,
        authorization: AuthorizationService | None = None,
    ) -> None:
        self._data_mapper = data_mapper
        self._life365_api_gateway = life365_api_gateway
        self._authorization = authorization or AuthorizationService()

    async def get_products(
        self, user: AuthenticatedUser, limit: int = 100, offset: int = 0
    ) -> list[ProductDTO]:
        try:
            self._authorization.require_permission(
                user.permissions, Permission.PRODUCTS_LIST
            )
            products: list[Product] = await self._data_mapper.get_products(
                limit=limit, offset=offset
            )
            allowed_products: list[Product] = [
                product
                for product in products
                if self._authorization.matches_product_scope(
                    product=product, scope=user.product_access.list
                )
            ]
            return [product_to_dto(product) for product in allowed_products]
        except AuthorizationException:
            raise
        except Exception as e:
            raise DBException("Products lookup failed") from e

    async def get_product(self, user: AuthenticatedUser, product_id: int) -> ProductDTO:
        try:
            self._authorization.require_permission(
                user.permissions, Permission.PRODUCTS_READ
            )
            product: Product = await self._data_mapper.get_product(product_id)
            self._authorization.require_product_access(
                product=product, scope=user.product_access.read
            )
            return product_to_dto(product)
        except AuthorizationException:
            raise
        except Exception as e:
            raise DBException("Product lookup failed") from e

    async def recommend_products(
        self,
        user: AuthenticatedUser,
        order_id: int | None = None,
        customer_id: int | None = None,
    ) -> object:
        return await self._life365_api_gateway.recommend_products(
            order_id=order_id, customer_id=customer_id
        )
