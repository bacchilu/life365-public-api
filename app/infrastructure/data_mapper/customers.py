from app.application.domain import Customer
from app.application.ports import CustomersGateway


class CustomersDataMapper(CustomersGateway):
    def __init__(self) -> None:
        self._customers: tuple[Customer, ...] = (
            Customer(
                id=1,
                login="customer-login",
                email="customer@example.com",
                business_name="Example Business",
                business_contact_name="Example Contact",
                preferred_language="it",
            ),
            Customer(
                id=2,
                login="second-customer",
                email="second.customer@example.com",
                business_name="Second Business",
                business_contact_name="Second Contact",
                preferred_language="en",
            ),
        )

    async def get_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        return list(self._customers[offset : offset + limit])
