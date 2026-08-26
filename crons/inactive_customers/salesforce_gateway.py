from collections.abc import AsyncIterator
from typing import Protocol

from crons.inactive_customers.model import CustomerSyncResult, InactiveCustomer


class SalesforceGateway(Protocol):
    def sync_inactive_customers(
        self, customers: list[InactiveCustomer], access_token: str
    ) -> AsyncIterator[list[CustomerSyncResult]]: ...
