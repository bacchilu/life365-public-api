import pytest

from app.application.domain import (
    ActiveProductsScope,
    AllProductsScope,
    AuthenticatedUser,
    NoProductCreateScope,
    NoProductsScope,
    OwnerProductsScope,
    Permission,
    PrincipalType,
    Product,
    ProductAccessPolicy,
    ProductScope,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.exceptions import AuthorizationException
from app.application.ports import CheckGateway, ProductsGateway
from app.application.services.health_service import HealthService
from app.application.services.products_service import ProductsService


class FakeCheckGateway(CheckGateway):
    async def check_db(self) -> bool:
        return True


class FakeProductsGateway(ProductsGateway):
    def __init__(
        self,
        products: list[Product] | None = None,
        product: Product | None = None,
    ) -> None:
        self.products: list[Product] = (
            products
            if products is not None
            else [
                Product(
                    id=1,
                    vendor_code="vendor",
                    isin="isin",
                    titles={"en": "Product"},
                    descriptions={"en": "Description"},
                    enabled=True,
                    barcodes=("123",),
                )
            ]
        )
        self.product = product
        self.products_requests: list[tuple[int, int]] = []
        self.product_requests: list[int] = []

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        self.products_requests.append((limit, offset))
        return self.products

    async def get_product(self, product_id: int) -> Product:
        self.product_requests.append(product_id)

        if self.product is not None:
            return self.product

        return Product(
            id=product_id,
            vendor_code="single",
            isin="single-isin",
            enabled=True,
        )


def _authenticated_user(
    *,
    principal_id: int = 1,
    username: str = "admin",
    role: Role = Role.ADMIN,
    principal_type: PrincipalType = PrincipalType.USER,
    permissions: frozenset[Permission] | None = None,
    product_access: ProductAccessPolicy | None = None,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=principal_id,
        username=username,
        role=role,
        principal_type=principal_type,
        token_id="token-id",
        permissions=(
            permissions if permissions is not None else resolve_permissions(role)
        ),
        product_access=(
            product_access
            if product_access is not None
            else resolve_product_access_policy(role, user_id=principal_id)
        ),
    )


def _product_access_policy(
    *,
    list_scope: ProductScope | None = None,
    read_scope: ProductScope | None = None,
) -> ProductAccessPolicy:
    return ProductAccessPolicy(
        create=NoProductCreateScope(),
        list=list_scope if list_scope is not None else AllProductsScope(),
        read=read_scope if read_scope is not None else AllProductsScope(),
        update=NoProductsScope(),
        delete=NoProductsScope(),
    )


@pytest.mark.parametrize(
    ("role", "principal_type"),
    [
        (Role.ADMIN, PrincipalType.USER),
        (Role.BUYER, PrincipalType.USER),
        (Role.CUSTOMER, PrincipalType.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_products_service_get_products_allows_read_roles(
    role: Role,
    principal_type: PrincipalType,
) -> None:
    gateway = FakeProductsGateway(
        products=[
            Product(id=1, vendor_code="first", isin="first-isin", enabled=True),
            Product(id=2, vendor_code="second", isin="second-isin", enabled=True),
        ]
    )
    service = ProductsService(gateway)
    user = _authenticated_user(
        role=role,
        principal_type=principal_type,
    )

    products = await service.get_products(user=user, limit=25, offset=5)

    assert [product.id for product in products] == [1, 2]
    assert [product.vendor_code for product in products] == ["first", "second"]
    assert gateway.products_requests == [(25, 5)]


@pytest.mark.parametrize(
    ("role", "principal_type"),
    [
        (Role.ADMIN, PrincipalType.USER),
        (Role.BUYER, PrincipalType.USER),
        (Role.CUSTOMER, PrincipalType.CUSTOMER),
    ],
)
@pytest.mark.anyio
async def test_products_service_get_product_allows_read_roles(
    role: Role,
    principal_type: PrincipalType,
) -> None:
    gateway = FakeProductsGateway(
        product=Product(
            id=7,
            vendor_code="single",
            isin="single-isin",
            enabled=True,
        )
    )
    service = ProductsService(gateway)
    user = _authenticated_user(
        role=role,
        principal_type=principal_type,
    )

    product = await service.get_product(user=user, product_id=7)

    assert product.id == 7
    assert product.vendor_code == "single"
    assert product.isin == "single-isin"
    assert gateway.product_requests == [7]


@pytest.mark.anyio
async def test_health_service_uses_check_gateway() -> None:
    gateway: CheckGateway = FakeCheckGateway()
    service = HealthService(gateway)

    assert service.health() is True
    assert await service.check_db() is True


@pytest.mark.anyio
async def test_products_service_get_products_uses_products_gateway() -> None:
    gateway = FakeProductsGateway()
    service = ProductsService(gateway)
    user = _authenticated_user()

    products = await service.get_products(user=user, limit=10, offset=0)

    assert len(products) == 1
    assert products[0].id == 1
    assert products[0].vendor_code == "vendor"
    assert products[0].isin == "isin"
    assert products[0].titles == {"en": "Product"}
    assert products[0].descriptions == {"en": "Description"}
    assert products[0].enabled is True
    assert products[0].barcodes == ("123",)
    assert gateway.products_requests == [(10, 0)]


@pytest.mark.anyio
async def test_products_service_get_product_uses_products_gateway() -> None:
    gateway = FakeProductsGateway()
    service = ProductsService(gateway)
    user = _authenticated_user()

    product = await service.get_product(user=user, product_id=7)

    assert product.id == 7
    assert product.vendor_code == "single"
    assert product.isin == "single-isin"
    assert product.enabled is True
    assert gateway.product_requests == [7]


@pytest.mark.anyio
async def test_products_service_get_products_requires_list_permission() -> None:
    gateway = FakeProductsGateway()
    service = ProductsService(gateway)
    user = _authenticated_user(permissions=frozenset({Permission.PRODUCTS_READ}))

    with pytest.raises(AuthorizationException, match="Missing required permission"):
        await service.get_products(user=user)

    assert gateway.products_requests == []


@pytest.mark.anyio
async def test_products_service_get_product_requires_read_permission() -> None:
    gateway = FakeProductsGateway()
    service = ProductsService(gateway)
    user = _authenticated_user(permissions=frozenset({Permission.PRODUCTS_LIST}))

    with pytest.raises(AuthorizationException, match="Missing required permission"):
        await service.get_product(user=user, product_id=7)

    assert gateway.product_requests == []


@pytest.mark.anyio
async def test_products_service_get_products_applies_list_scope() -> None:
    gateway = FakeProductsGateway(
        products=[
            Product(id=1, vendor_code="enabled", isin="enabled", enabled=True),
            Product(id=2, vendor_code="disabled", isin="disabled", enabled=False),
        ]
    )
    service = ProductsService(gateway)
    user = _authenticated_user(
        permissions=frozenset({Permission.PRODUCTS_LIST}),
        product_access=_product_access_policy(list_scope=ActiveProductsScope()),
    )

    products = await service.get_products(user=user, limit=50, offset=25)

    assert [product.id for product in products] == [1]
    assert gateway.products_requests == [(50, 25)]


@pytest.mark.anyio
async def test_products_service_get_products_denied_scope_returns_empty_list() -> None:
    gateway = FakeProductsGateway(
        products=[
            Product(id=1, vendor_code="first", isin="first-isin", enabled=True),
            Product(id=2, vendor_code="second", isin="second-isin", enabled=True),
        ]
    )
    service = ProductsService(gateway)
    user = _authenticated_user(
        permissions=frozenset({Permission.PRODUCTS_LIST}),
        product_access=_product_access_policy(list_scope=NoProductsScope()),
    )

    products = await service.get_products(user=user, limit=50, offset=25)

    assert products == []
    assert gateway.products_requests == [(50, 25)]


@pytest.mark.anyio
async def test_products_service_get_product_applies_read_scope() -> None:
    gateway = FakeProductsGateway(
        product=Product(
            id=7,
            vendor_code="single",
            isin="single-isin",
            owner_id=20,
            enabled=True,
        )
    )
    service = ProductsService(gateway)
    user = _authenticated_user(
        permissions=frozenset({Permission.PRODUCTS_READ}),
        product_access=_product_access_policy(
            read_scope=OwnerProductsScope(owner_id=10)
        ),
    )

    with pytest.raises(AuthorizationException, match="outside allowed scope"):
        await service.get_product(user=user, product_id=7)

    assert gateway.product_requests == [7]
