from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from app.application.domain import (
    ActiveProductsScope,
    AllProductCreateScope,
    AllProductsScope,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductCreateScope,
    OwnerProductsScope,
    Permission,
    ProductAccessPolicy,
    SpecificProductsScope,
)
from app.application.exceptions import AuthorizationException


def test_permission_values_match_product_actions() -> None:
    assert Permission.PRODUCTS_CREATE.value == "products:create"
    assert Permission.PRODUCTS_LIST.value == "products:list"
    assert Permission.PRODUCTS_READ.value == "products:read"
    assert Permission.PRODUCTS_UPDATE.value == "products:update"
    assert Permission.PRODUCTS_DELETE.value == "products:delete"


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
