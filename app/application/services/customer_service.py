from app.application.domain import Customer
from app.application.exceptions import DBException
from app.application.ports import CustomersGateway


class CustomerService:
    def __init__(self, data_mapper: CustomersGateway) -> None:
        self._data_mapper = data_mapper

    async def get_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        try:
            return await self._data_mapper.get_customers(limit=limit, offset=offset)
        except Exception as exc:
            raise DBException("Customers lookup failed") from exc
