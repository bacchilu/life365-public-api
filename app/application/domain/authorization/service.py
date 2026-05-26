__all__ = ["AuthorizationService"]


from app.application.domain.authorization.permissions import Permission
from app.application.domain.authorization.scopes import (
    ActiveProductsScope,
    AllProductCreateScope,
    AllProductsScope,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductCreateScope,
    OwnerProductsScope,
    ProductCreateScope,
    ProductScope,
    SpecificProductsScope,
)
from app.application.domain.product import Product
from app.application.exceptions import AuthorizationException


class AuthorizationService:
    def require_permission(
        self, permissions: frozenset[Permission], permission: Permission
    ) -> None:
        if permission not in permissions:
            raise AuthorizationException(f"Missing required permission: {permission}")

    def require_product_access(self, product: Product, scope: ProductScope) -> None:
        if not self.matches_product_scope(product=product, scope=scope):
            raise AuthorizationException("Product is outside allowed scope")

    def require_product_create_access(
        self, owner_id: int | None, scope: ProductCreateScope
    ) -> None:
        if not self.matches_product_create_scope(owner_id=owner_id, scope=scope):
            raise AuthorizationException("Product creation is outside allowed scope")

    def matches_product_scope(self, product: Product, scope: ProductScope) -> bool:
        if isinstance(scope, AllProductsScope):
            return True

        if isinstance(scope, ActiveProductsScope):
            return product.enabled is True

        if isinstance(scope, OwnerProductsScope):
            return product.owner_id == scope.owner_id

        if isinstance(scope, SpecificProductsScope):
            return product.id in scope.product_ids

        if isinstance(scope, NoProductsScope):
            return False

        return False

    def matches_product_create_scope(
        self, owner_id: int | None, scope: ProductCreateScope
    ) -> bool:
        if isinstance(scope, AllProductCreateScope):
            return True

        if isinstance(scope, OwnerProductCreateScope):
            return owner_id == scope.owner_id

        if isinstance(scope, NoProductCreateScope):
            return False

        return False
