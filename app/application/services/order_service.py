from app.application.domain import Order
from app.application.exceptions import DBException
from app.application.ports import OrdersGateway


class OrderService:
    def __init__(self, data_mapper: OrdersGateway) -> None:
        self._data_mapper = data_mapper

    async def get_orders(self, limit: int = 100, offset: int = 0) -> list[Order]:
        try:
            return await self._data_mapper.get_orders(limit=limit, offset=offset)
        except Exception as exc:
            raise DBException("Orders lookup failed") from exc
