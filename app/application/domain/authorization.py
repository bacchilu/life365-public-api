__all__ = [
    "ActiveProductsScope",
    "AllProductCreateScope",
    "AllProductsScope",
    "NoProductCreateScope",
    "NoProductsScope",
    "OwnerProductCreateScope",
    "OwnerProductsScope",
    "Permission",
    "ProductAccessPolicy",
    "ProductCreateScope",
    "ProductScope",
    "SpecificProductsScope",
]


from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class Permission(StrEnum):
    PRODUCTS_CREATE = "products:create"
    PRODUCTS_LIST = "products:list"
    PRODUCTS_READ = "products:read"
    PRODUCTS_UPDATE = "products:update"
    PRODUCTS_DELETE = "products:delete"


def _validate_positive_int(value: int, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class AllProductsScope:
    pass


@dataclass(frozen=True, slots=True)
class ActiveProductsScope:
    pass


@dataclass(frozen=True, slots=True)
class OwnerProductsScope:
    owner_id: int

    def __post_init__(self) -> None:
        _validate_positive_int(self.owner_id, "owner_id")


@dataclass(frozen=True, slots=True)
class SpecificProductsScope:
    product_ids: frozenset[int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_ids", frozenset(self.product_ids))

    @classmethod
    def from_ids(cls, product_ids: Iterable[int]) -> "SpecificProductsScope":
        return cls(product_ids=frozenset(product_ids))


@dataclass(frozen=True, slots=True)
class NoProductsScope:
    pass


ProductScope: TypeAlias = (
    AllProductsScope
    | ActiveProductsScope
    | OwnerProductsScope
    | SpecificProductsScope
    | NoProductsScope
)


@dataclass(frozen=True, slots=True)
class AllProductCreateScope:
    pass


@dataclass(frozen=True, slots=True)
class OwnerProductCreateScope:
    owner_id: int

    def __post_init__(self) -> None:
        _validate_positive_int(self.owner_id, "owner_id")


@dataclass(frozen=True, slots=True)
class NoProductCreateScope:
    pass


ProductCreateScope: TypeAlias = (
    AllProductCreateScope | OwnerProductCreateScope | NoProductCreateScope
)


@dataclass(frozen=True, slots=True)
class ProductAccessPolicy:
    create: ProductCreateScope
    list: ProductScope
    read: ProductScope
    update: ProductScope
    delete: ProductScope
