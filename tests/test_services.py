import pytest

from app.application.domain import Product
from app.application.ports import CheckGateway, ProductsGateway
from app.application.services.health_service import HealthService
from app.application.services.products_service import ProductsService


class FakeCheckGateway(CheckGateway):
    async def check_db(self) -> bool:
        return True


class FakeProductsGateway(ProductsGateway):
    def __init__(self) -> None:
        self.product = Product(
            id=1,
            vendor_code="vendor",
            isin="isin",
            titles={"en": "Product"},
            descriptions={"en": "Description"},
            enabled=True,
            barcodes=("123",),
        )

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        return [self.product]

    async def get_product(self, product_id: int) -> Product:
        return Product(
            id=product_id,
            vendor_code="single",
            isin="single-isin",
            enabled=True,
        )


@pytest.mark.anyio
async def test_health_service_uses_check_gateway() -> None:
    gateway: CheckGateway = FakeCheckGateway()
    service = HealthService(gateway)

    assert service.health() is True
    assert await service.check_db() is True


@pytest.mark.anyio
async def test_products_service_get_products_uses_products_gateway() -> None:
    gateway: ProductsGateway = FakeProductsGateway()
    service = ProductsService(gateway)

    products = await service.get_products(limit=10, offset=0)

    assert len(products) == 1
    assert products[0].id == 1
    assert products[0].vendor_code == "vendor"
    assert products[0].isin == "isin"
    assert products[0].titles == {"en": "Product"}
    assert products[0].descriptions == {"en": "Description"}
    assert products[0].enabled is True
    assert products[0].barcodes == ("123",)


@pytest.mark.anyio
async def test_products_service_get_product_uses_products_gateway() -> None:
    gateway: ProductsGateway = FakeProductsGateway()
    service = ProductsService(gateway)

    product = await service.get_product(7)

    assert product.id == 7
    assert product.vendor_code == "single"
    assert product.isin == "single-isin"
    assert product.enabled is True
