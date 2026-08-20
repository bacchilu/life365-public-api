import pytest

from app.application.domain import Order
from app.application.ports import OrdersGateway
from app.application.services.order_service import OrderService


class FakeOrdersGateway(OrdersGateway):
    def __init__(self, orders: list[Order]) -> None:
        self._orders = orders
        self.requests: list[tuple[int, int]] = []

    async def get_orders(self, limit: int = 100, offset: int = 0) -> list[Order]:
        self.requests.append((limit, offset))
        return self._orders


@pytest.mark.anyio
async def test_order_service_delegates_to_orders_gateway() -> None:
    gateway = FakeOrdersGateway([])
    service = OrderService(gateway)

    assert await service.get_orders(limit=25, offset=50) == []
    assert gateway.requests == [(25, 50)]
