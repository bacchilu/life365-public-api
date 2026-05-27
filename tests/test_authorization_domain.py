from dataclasses import FrozenInstanceError, is_dataclass
from typing import cast

import pytest

from app.application.domain import (
    ROLE_PERMISSIONS,
    ActiveProductsScope,
    AllProductCreateScope,
    AllProductsScope,
    AuthorizationService,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductCreateScope,
    OwnerProductsScope,
    Permission,
    Product,
    ProductAccessPolicy,
    ProductCreateScope,
    ProductScope,
    Role,
    SpecificProductsScope,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.exceptions import AuthorizationException


def test_permission_values_match_product_actions() -> None:
    assert Permission.PRODUCTS_CREATE.value == "products:create"
    assert Permission.PRODUCTS_LIST.value == "products:list"
    assert Permission.PRODUCTS_READ.value == "products:read"
    assert Permission.PRODUCTS_UPDATE.value == "products:update"
    assert Permission.PRODUCTS_DELETE.value == "products:delete"


def test_role_permissions_are_declared_for_supported_roles() -> None:
    assert set(ROLE_PERMISSIONS) == {Role.ADMIN, Role.BUYER, Role.CUSTOMER}


@pytest.mark.parametrize(
    "scope_type",
    [
        AllProductsScope,
        ActiveProductsScope,
        OwnerProductsScope,
        SpecificProductsScope,
        NoProductsScope,
        AllProductCreateScope,
        OwnerProductCreateScope,
        NoProductCreateScope,
    ],
)
def test_scope_classes_are_frozen_slotted_dataclasses(
    scope_type: type[object],
) -> None:
    assert is_dataclass(scope_type)
    assert scope_type.__dataclass_params__.frozen is True
    assert hasattr(scope_type, "__slots__")


def test_product_scopes_are_immutable() -> None:
    scope = OwnerProductsScope(owner_id=10)

    with pytest.raises(FrozenInstanceError):
        scope.owner_id = 20


def test_product_create_scopes_are_immutable() -> None:
    scope = OwnerProductCreateScope(owner_id=10)

    with pytest.raises(FrozenInstanceError):
        scope.owner_id = 20


def test_owner_product_scope_carries_owner_id() -> None:
    scope = OwnerProductsScope(owner_id=10)

    assert scope.owner_id == 10


def test_owner_product_create_scope_carries_owner_id() -> None:
    scope = OwnerProductCreateScope(owner_id=10)

    assert scope.owner_id == 10


@pytest.mark.parametrize("owner_id", [0, -1, True])
def test_owner_product_scope_requires_positive_integer(owner_id: int) -> None:
    with pytest.raises(ValueError, match="owner_id must be a positive integer"):
        OwnerProductsScope(owner_id=owner_id)


@pytest.mark.parametrize("owner_id", [0, -1, True])
def test_owner_product_create_scope_requires_positive_integer(
    owner_id: int,
) -> None:
    with pytest.raises(ValueError, match="owner_id must be a positive integer"):
        OwnerProductCreateScope(owner_id=owner_id)


def test_specific_products_scope_normalizes_ids_to_frozenset() -> None:
    scope = SpecificProductsScope.from_ids([1, 2, 2, 3])

    assert scope.product_ids == frozenset({1, 2, 3})


def test_product_access_policy_accepts_scope_variants() -> None:
    policy = ProductAccessPolicy(
        create=AllProductCreateScope(),
        list=AllProductsScope(),
        read=ActiveProductsScope(),
        update=OwnerProductsScope(owner_id=10),
        delete=SpecificProductsScope.from_ids([1, 2]),
    )

    assert isinstance(policy.create, AllProductCreateScope)
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, ActiveProductsScope)
    assert isinstance(policy.update, OwnerProductsScope)
    assert isinstance(policy.delete, SpecificProductsScope)


def test_product_access_policy_accepts_no_access_scopes() -> None:
    policy = ProductAccessPolicy(
        create=NoProductCreateScope(),
        list=NoProductsScope(),
        read=NoProductsScope(),
        update=NoProductsScope(),
        delete=NoProductsScope(),
    )

    assert isinstance(policy.create, NoProductCreateScope)
    assert isinstance(policy.list, NoProductsScope)
    assert isinstance(policy.read, NoProductsScope)
    assert isinstance(policy.update, NoProductsScope)
    assert isinstance(policy.delete, NoProductsScope)


def test_authorization_exception_is_application_exception() -> None:
    exception = AuthorizationException("Forbidden")

    assert isinstance(exception, Exception)
    assert str(exception) == "Forbidden"


def test_authorization_service_is_importable_from_domain_package() -> None:
    service = AuthorizationService()

    assert isinstance(service, AuthorizationService)


def test_admin_permission_resolution_returns_all_product_permissions() -> None:
    assert resolve_permissions(Role.ADMIN) == frozenset(
        {
            Permission.PRODUCTS_CREATE,
            Permission.PRODUCTS_LIST,
            Permission.PRODUCTS_READ,
            Permission.PRODUCTS_UPDATE,
            Permission.PRODUCTS_DELETE,
        }
    )


def test_buyer_permission_resolution_returns_all_product_permissions() -> None:
    assert resolve_permissions(Role.BUYER) == frozenset(
        {
            Permission.PRODUCTS_CREATE,
            Permission.PRODUCTS_LIST,
            Permission.PRODUCTS_READ,
            Permission.PRODUCTS_UPDATE,
            Permission.PRODUCTS_DELETE,
        }
    )


def test_customer_permission_resolution_returns_list_and_read_only() -> None:
    assert resolve_permissions(Role.CUSTOMER) == frozenset(
        {
            Permission.PRODUCTS_LIST,
            Permission.PRODUCTS_READ,
        }
    )


@pytest.mark.parametrize("role", ["admin", object(), None])
def test_unsupported_role_permission_resolution_returns_no_permissions(
    role: object,
) -> None:
    assert resolve_permissions(role) == frozenset()


def test_admin_product_access_policy_uses_all_scopes() -> None:
    policy = resolve_product_access_policy(Role.ADMIN)

    assert isinstance(policy.create, AllProductCreateScope)
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, AllProductsScope)
    assert isinstance(policy.delete, AllProductsScope)


def test_buyer_product_access_policy_uses_owner_mutation_scopes() -> None:
    policy = resolve_product_access_policy(Role.BUYER, user_id=10)

    assert isinstance(policy.create, OwnerProductCreateScope)
    assert policy.create.owner_id == 10
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, OwnerProductsScope)
    assert policy.update.owner_id == 10
    assert isinstance(policy.delete, OwnerProductsScope)
    assert policy.delete.owner_id == 10


@pytest.mark.parametrize("user_id", [None, 0, -1, True])
def test_buyer_product_access_policy_fails_closed_for_invalid_user_id(
    user_id: int | None,
) -> None:
    policy = resolve_product_access_policy(Role.BUYER, user_id=user_id)

    assert isinstance(policy.create, NoProductCreateScope)
    assert isinstance(policy.list, NoProductsScope)
    assert isinstance(policy.read, NoProductsScope)
    assert isinstance(policy.update, NoProductsScope)
    assert isinstance(policy.delete, NoProductsScope)


def test_customer_product_access_policy_uses_read_only_product_access() -> None:
    policy = resolve_product_access_policy(Role.CUSTOMER)

    assert isinstance(policy.create, NoProductCreateScope)
    assert isinstance(policy.list, AllProductsScope)
    assert isinstance(policy.read, AllProductsScope)
    assert isinstance(policy.update, NoProductsScope)
    assert isinstance(policy.delete, NoProductsScope)


@pytest.mark.parametrize("role", ["customer", object(), None])
def test_unsupported_role_product_access_policy_returns_no_access(
    role: object,
) -> None:
    policy = resolve_product_access_policy(role)

    assert isinstance(policy.create, NoProductCreateScope)
    assert isinstance(policy.list, NoProductsScope)
    assert isinstance(policy.read, NoProductsScope)
    assert isinstance(policy.update, NoProductsScope)
    assert isinstance(policy.delete, NoProductsScope)


def test_authorization_service_allows_present_permission() -> None:
    service = AuthorizationService()

    service.require_permission(
        permissions=frozenset({Permission.PRODUCTS_READ}),
        permission=Permission.PRODUCTS_READ,
    )


def test_authorization_service_rejects_missing_permission() -> None:
    service = AuthorizationService()

    with pytest.raises(AuthorizationException, match="Missing required permission"):
        service.require_permission(
            permissions=frozenset({Permission.PRODUCTS_LIST}),
            permission=Permission.PRODUCTS_READ,
        )


def test_authorization_service_matches_all_products_scope() -> None:
    service = AuthorizationService()
    product = _product()

    assert service.matches_product_scope(product, AllProductsScope()) is True


def test_authorization_service_matches_active_products_scope() -> None:
    service = AuthorizationService()

    assert (
        service.matches_product_scope(_product(enabled=True), ActiveProductsScope())
        is True
    )
    assert (
        service.matches_product_scope(_product(enabled=False), ActiveProductsScope())
        is False
    )


def test_authorization_service_matches_owner_products_scope() -> None:
    service = AuthorizationService()
    scope = OwnerProductsScope(owner_id=10)

    assert service.matches_product_scope(_product(owner_id=10), scope) is True
    assert service.matches_product_scope(_product(owner_id=20), scope) is False
    assert service.matches_product_scope(_product(owner_id=None), scope) is False


def test_authorization_service_matches_specific_products_scope() -> None:
    service = AuthorizationService()
    scope = SpecificProductsScope.from_ids([1, 2])

    assert service.matches_product_scope(_product(id=1), scope) is True
    assert service.matches_product_scope(_product(id=3), scope) is False


def test_authorization_service_rejects_no_products_scope() -> None:
    service = AuthorizationService()

    assert service.matches_product_scope(_product(), NoProductsScope()) is False


def test_authorization_service_fails_closed_for_unknown_product_scope() -> None:
    service = AuthorizationService()

    assert (
        service.matches_product_scope(
            _product(),
            cast(ProductScope, object()),
        )
        is False
    )


def test_authorization_service_requires_product_access() -> None:
    service = AuthorizationService()

    service.require_product_access(
        product=_product(owner_id=10),
        scope=OwnerProductsScope(owner_id=10),
    )


def test_authorization_service_raises_for_denied_product_access() -> None:
    service = AuthorizationService()

    with pytest.raises(
        AuthorizationException, match="Product is outside allowed scope"
    ):
        service.require_product_access(
            product=_product(owner_id=20),
            scope=OwnerProductsScope(owner_id=10),
        )


@pytest.mark.parametrize(
    ("enabled", "scope"), [(False, ActiveProductsScope()), (True, NoProductsScope())]
)
def test_authorization_service_raises_for_denied_product_scope_variants(
    enabled: bool, scope: ProductScope
) -> None:
    service = AuthorizationService()

    with pytest.raises(
        AuthorizationException, match="Product is outside allowed scope"
    ):
        service.require_product_access(product=_product(enabled=enabled), scope=scope)


def test_authorization_service_matches_all_product_create_scope() -> None:
    service = AuthorizationService()

    assert (
        service.matches_product_create_scope(
            owner_id=None,
            scope=AllProductCreateScope(),
        )
        is True
    )


def test_authorization_service_matches_owner_product_create_scope() -> None:
    service = AuthorizationService()
    scope = OwnerProductCreateScope(owner_id=10)

    assert service.matches_product_create_scope(owner_id=10, scope=scope) is True
    assert service.matches_product_create_scope(owner_id=20, scope=scope) is False
    assert service.matches_product_create_scope(owner_id=None, scope=scope) is False


def test_authorization_service_rejects_no_product_create_scope() -> None:
    service = AuthorizationService()

    assert (
        service.matches_product_create_scope(
            owner_id=10,
            scope=NoProductCreateScope(),
        )
        is False
    )


def test_authorization_service_fails_closed_for_unknown_create_scope() -> None:
    service = AuthorizationService()

    assert (
        service.matches_product_create_scope(
            owner_id=10,
            scope=cast(ProductCreateScope, object()),
        )
        is False
    )


def test_authorization_service_requires_product_create_access() -> None:
    service = AuthorizationService()

    service.require_product_create_access(
        owner_id=10,
        scope=OwnerProductCreateScope(owner_id=10),
    )


def test_authorization_service_raises_for_denied_product_create_access() -> None:
    service = AuthorizationService()

    with pytest.raises(
        AuthorizationException,
        match="Product creation is outside allowed scope",
    ):
        service.require_product_create_access(
            owner_id=None,
            scope=OwnerProductCreateScope(owner_id=10),
        )


def test_authorization_service_raises_for_no_product_create_scope() -> None:
    service = AuthorizationService()

    with pytest.raises(
        AuthorizationException,
        match="Product creation is outside allowed scope",
    ):
        service.require_product_create_access(
            owner_id=10,
            scope=NoProductCreateScope(),
        )


def _product(
    id: int = 1,
    enabled: bool = True,
    owner_id: int | None = 10,
) -> Product:
    return Product(
        id=id,
        vendor_code="vendor",
        isin="isin",
        enabled=enabled,
        owner_id=owner_id,
    )
