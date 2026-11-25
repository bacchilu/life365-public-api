import os

from crons.inactive_customers.database import collect_inactive_customers
from crons.inactive_customers.mock_salesforce import MockSalesforceGateway
from crons.inactive_customers.model import CustomerSyncStatus
from crons.inactive_customers.salesforce import request_salesforce_access_token
from crons.inactive_customers.salesforce_gateway import SalesforceGateway


async def execute_workflow(salesforce_gateway: SalesforceGateway | None = None) -> None:
    print("Starting phase 1: collect inactive customers", flush=True)
    customers = await collect_inactive_customers(
        _required_environment_variable("DATABASE_URL")
    )
    print(f"Completed phase 1: {len(customers)} customers found", flush=True)

    if not customers:
        print("No inactive customers to synchronize", flush=True)
        return

    print(
        "Starting phase 2: synchronize inactive customers with Salesforce",
        flush=True,
    )
    gateway = (
        MockSalesforceGateway() if salesforce_gateway is None else salesforce_gateway
    )
    access_token = await _request_access_token()
    succeeded = 0
    failed = 0
    async for results in gateway.sync_inactive_customers(customers, access_token):
        succeeded += sum(
            result.status is CustomerSyncStatus.SUCCEEDED for result in results
        )
        failed += sum(result.status is CustomerSyncStatus.FAILED for result in results)

    print(f"Completed phase 2: {succeeded} succeeded, {failed} failed", flush=True)


async def _request_access_token() -> str:
    access_token: str = await request_salesforce_access_token(
        _required_environment_variable("SALESFORCE_TOKEN_URL"),
        _required_environment_variable("SALESFORCE_CLIENT_ID"),
        _required_environment_variable("SALESFORCE_CLIENT_SECRET"),
    )
    print("Salesforce access token acquired successfully", flush=True)
    return access_token


def _required_environment_variable(name: str) -> str:
    value: str | None = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value
