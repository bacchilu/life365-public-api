from typing import Protocol

from crons.inactive_customers.model import InactiveCustomer


class SalesforceGateway(Protocol):
    async def sync_inactive_customers(
        self, customers: list[InactiveCustomer], access_token: str
    ) -> None: ...
