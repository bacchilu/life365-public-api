import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from crons.inactive_customers.database import collect_inactive_customers
from crons.inactive_customers.locking import acquire_job_lock
from crons.inactive_customers.mock_salesforce import MockSalesforceGateway
from crons.inactive_customers.model import InactiveCustomer
from crons.inactive_customers.salesforce import request_salesforce_access_token
from crons.inactive_customers.salesforce_gateway import SalesforceGateway
from crons.inactive_customers.snapshot import write_inactive_customers

DEFAULT_OUTPUT_PATH: Path = Path("data/inactive-customers.json")


def required_environment_variable(name: str) -> str:
    value: str | None = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


async def run() -> None:
    load_dotenv()
    connection_string: str = required_environment_variable("DATABASE_URL")
    salesforce_token_url: str = required_environment_variable(
        "SALESFORCE_TOKEN_URL"
    )
    salesforce_client_id: str = required_environment_variable(
        "SALESFORCE_CLIENT_ID"
    )
    salesforce_client_secret: str = required_environment_variable(
        "SALESFORCE_CLIENT_SECRET"
    )
    output_path = Path(
        os.environ.get("INACTIVE_CUSTOMERS_OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH))
    )

    lock_path = output_path.with_suffix(".lock")
    with acquire_job_lock(lock_path) as acquired:
        if not acquired:
            print(
                "Inactive customer collection is already running; "
                "skipping this execution",
                flush=True,
            )
            return

        print("Starting phase 1: collect inactive customers", flush=True)
        customers: list[InactiveCustomer] = await collect_inactive_customers(
            connection_string
        )
        await asyncio.to_thread(
            write_inactive_customers,
            output_path,
            customers,
            datetime.now(timezone.utc),
        )

        print(
            "Completed phase 1: "
            f"{len(customers)} customers written to {output_path}",
            flush=True,
        )

        print(
            "Starting phase 2: synchronize inactive customers with Salesforce",
            flush=True,
        )
        salesforce_access_token: str = await request_salesforce_access_token(
            salesforce_token_url,
            salesforce_client_id,
            salesforce_client_secret,
        )
        print("Salesforce access token acquired successfully", flush=True)

        salesforce_gateway: SalesforceGateway = MockSalesforceGateway()
        await salesforce_gateway.sync_inactive_customers(
            customers,
            salesforce_access_token,
        )
        print(
            "Completed phase 2: inactive customer synchronization completed",
            flush=True,
        )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
