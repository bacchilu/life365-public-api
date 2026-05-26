__all__ = ["ProductAccessPolicy", "resolve_product_access_policy"]


from dataclasses import dataclass

from app.application.domain.auth import Role
from app.application.domain.authorization.scopes import (
    AllProductCreateScope,
    AllProductsScope,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductCreateScope,
    OwnerProductsScope,
    ProductCreateScope,
    ProductScope,
)


@dataclass(frozen=True, slots=True)
class ProductAccessPolicy:
    create: ProductCreateScope
    list: ProductScope
    read: ProductScope
    update: ProductScope
    delete: ProductScope


def resolve_product_access_policy(
    role: object,
    user_id: int | None = None,
) -> ProductAccessPolicy:
    if role is Role.ADMIN:
        return ProductAccessPolicy(
            create=AllProductCreateScope(),
            list=AllProductsScope(),
            read=AllProductsScope(),
            update=AllProductsScope(),
            delete=AllProductsScope(),
        )

    if role is Role.BUYER:
        buyer_user_id = _positive_int_or_none(user_id)
        if buyer_user_id is None:
            return _no_product_access_policy()

        return ProductAccessPolicy(
            create=OwnerProductCreateScope(owner_id=buyer_user_id),
            list=AllProductsScope(),
            read=AllProductsScope(),
            update=OwnerProductsScope(owner_id=buyer_user_id),
            delete=OwnerProductsScope(owner_id=buyer_user_id),
        )

    if role is Role.CUSTOMER:
        return ProductAccessPolicy(
            create=NoProductCreateScope(),
            list=AllProductsScope(),
            read=AllProductsScope(),
            update=NoProductsScope(),
            delete=NoProductsScope(),
        )

    return _no_product_access_policy()


def _positive_int_or_none(value: object) -> int | None:
    if type(value) is not int or value <= 0:
        return None

    return value


def _no_product_access_policy() -> ProductAccessPolicy:
    return ProductAccessPolicy(
        create=NoProductCreateScope(),
        list=NoProductsScope(),
        read=NoProductsScope(),
        update=NoProductsScope(),
        delete=NoProductsScope(),
    )
