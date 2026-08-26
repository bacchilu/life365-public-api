import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from crons.inactive_customers.model import (
    CustomerSyncResult,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.salesforce_gateway import SalesforceGateway


class MockSalesforceGateway(SalesforceGateway):
    async def sync_inactive_customers(
        self, customers: list[InactiveCustomer], access_token: str
    ) -> AsyncIterator[list[CustomerSyncResult]]:
        print(
            f"Starting mock Salesforce sync for {len(customers)} customers", flush=True
        )
        delay_seconds: int = random.randint(5, 30)
        print(
            f"Mock Salesforce sync will take {delay_seconds} seconds", flush=True
        )
        await asyncio.sleep(delay_seconds)
        print("Mock Salesforce sync completed; no customer data was sent", flush=True)
        completed_at = datetime.now(timezone.utc)
        yield [
            CustomerSyncResult(
                customer_id=customer.id,
                status=CustomerSyncStatus.SUCCEEDED,
                completed_at=completed_at,
            )
            for customer in customers
        ]
