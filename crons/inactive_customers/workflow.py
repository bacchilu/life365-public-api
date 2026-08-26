import os
from datetime import datetime, timezone
from pathlib import Path

from crons.inactive_customers.database import collect_inactive_customers
from crons.inactive_customers.mock_salesforce import MockSalesforceGateway
from crons.inactive_customers.model import InactiveCustomer
from crons.inactive_customers.salesforce import request_salesforce_access_token
from crons.inactive_customers.salesforce_gateway import SalesforceGateway
from crons.inactive_customers.snapshot import (
    build_report_paths,
    write_inactive_customers,
)
from crons.inactive_customers.sync_store import (
    complete_sync_run,
    create_sync_database,
    load_pending_customers,
    load_sync_run,
    remove_sync_database,
    save_sync_results,
)


async def execute_workflow(
    output_path: Path,
    salesforce_gateway: SalesforceGateway | None = None,
) -> None:
    database_path: Path = output_path.with_suffix(".sqlite3")
    if database_path.exists():
        print(
            f"Found {database_path}; skipping phase 1 and resuming phase 2",
            flush=True,
        )
    else:
        await _execute_phase_one(database_path)

    await _execute_phase_two(
        database_path,
        output_path,
        salesforce_gateway or MockSalesforceGateway(),
    )


async def _execute_phase_one(database_path: Path) -> None:
    print("Starting phase 1: collect inactive customers", flush=True)
    customers: list[InactiveCustomer] = await collect_inactive_customers(
        _required_environment_variable("DATABASE_URL")
    )
    create_sync_database(
        database_path,
        customers,
        datetime.now(timezone.utc),
    )
    print(
        f"Completed phase 1: {len(customers)} customers stored in {database_path}",
        flush=True,
    )


async def _execute_phase_two(
    database_path: Path,
    output_path: Path,
    salesforce_gateway: SalesforceGateway,
) -> None:
    print(
        "Starting phase 2: synchronize inactive customers with Salesforce",
        flush=True,
    )
    customers: list[InactiveCustomer] = load_pending_customers(database_path)
    if customers:
        access_token: str = await _request_access_token()
        async for results in salesforce_gateway.sync_inactive_customers(
            customers, access_token
        ):
            save_sync_results(database_path, results)
    else:
        print("No pending customers remain in the sync database", flush=True)

    completed_at = datetime.now(timezone.utc)
    complete_sync_run(database_path, completed_at)
    print(
        "Completed phase 2: inactive customer synchronization completed",
        flush=True,
    )

    run, records = load_sync_run(database_path)
    if run.completed_at is None:
        raise RuntimeError("Completed sync run does not have a completion timestamp")
    report_path, latest_path = build_report_paths(output_path, run.completed_at)
    write_inactive_customers(report_path, run, records)
    write_inactive_customers(latest_path, run, records)
    remove_sync_database(database_path)
    print(f"Final customer sync report written to {report_path}", flush=True)
    print(f"Latest customer sync report written to {latest_path}", flush=True)


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
