__all__ = ["Permission", "ROLE_PERMISSIONS", "resolve_permissions"]


from enum import StrEnum

from app.application.domain.identity import Role


class Permission(StrEnum):
    PRODUCTS_CREATE = "products:create"
    PRODUCTS_LIST = "products:list"
    PRODUCTS_READ = "products:read"
    PRODUCTS_UPDATE = "products:update"
    PRODUCTS_DELETE = "products:delete"


_ALL_PRODUCT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PRODUCTS_CREATE,
        Permission.PRODUCTS_LIST,
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_UPDATE,
        Permission.PRODUCTS_DELETE,
    }
)


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: _ALL_PRODUCT_PERMISSIONS,
    Role.BUYER: _ALL_PRODUCT_PERMISSIONS,
    Role.CUSTOMER: frozenset({Permission.PRODUCTS_LIST, Permission.PRODUCTS_READ}),
}


def resolve_permissions(role: object) -> frozenset[Permission]:
    if not isinstance(role, Role):
        return frozenset()

    return ROLE_PERMISSIONS.get(role, frozenset())
