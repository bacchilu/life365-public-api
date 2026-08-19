import pytest

from app.application.domain import Customer
from app.application.ports import CustomersGateway
from app.infrastructure.data_mapper import CustomersDataMapper


@pytest.mark.anyio
async def test_customers_data_mapper_paginates_in_memory_customers() -> None:
    gateway: CustomersGateway = CustomersDataMapper()

    customers = await gateway.get_customers(limit=1, offset=1)

    assert customers == [
        Customer(
            id=2,
            login="second-customer",
            email="second.customer@example.com",
            business_name="Second Business",
            business_contact_name="Second Contact",
            preferred_language="en",
        )
    ]


@pytest.mark.anyio
async def test_customers_data_mapper_rejects_invalid_pagination() -> None:
    gateway = CustomersDataMapper()

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await gateway.get_customers(limit=0)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        await gateway.get_customers(offset=-1)
