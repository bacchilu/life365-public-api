import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from crons.inactive_customers import workflow
from crons.inactive_customers.model import (
    CustomerSyncResult,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.salesforce_gateway import SalesforceGateway
from crons.inactive_customers.sync_store import (
    create_sync_database,
    load_pending_customers,
    save_sync_results,
)


class SuccessfulSalesforceGateway(SalesforceGateway):
    def __init__(self) -> None:
        self.received_customers: list[InactiveCustomer] = []

    async def sync_inactive_customers(
        self,
        customers: list[InactiveCustomer],
        access_token: str,
    ) -> AsyncIterator[list[CustomerSyncResult]]:
        self.received_customers = customers
        completed_at = datetime.now(timezone.utc)
        yield [
            CustomerSyncResult(
                customer_id=customer.id,
                status=CustomerSyncStatus.SUCCEEDED,
                completed_at=completed_at,
            )
            for customer in customers
        ]


class InterruptedSalesforceGateway(SalesforceGateway):
    async def sync_inactive_customers(
        self,
        customers: list[InactiveCustomer],
        access_token: str,
    ) -> AsyncIterator[list[CustomerSyncResult]]:
        yield [
            CustomerSyncResult(
                customer_id=customers[0].id,
                status=CustomerSyncStatus.SUCCEEDED,
                completed_at=datetime.now(timezone.utc),
            )
        ]
        raise RuntimeError("Salesforce connection failed")


@pytest.mark.anyio
async def test_workflow_creates_report_and_removes_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "inactive-customers.json"
    customers = [InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1))]
    collect = AsyncMock(return_value=customers)
    request_token = AsyncMock(return_value="test-access-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", "https://example.test/token")
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(workflow, "collect_inactive_customers", collect)
    monkeypatch.setattr(workflow, "request_salesforce_access_token", request_token)

    gateway = SuccessfulSalesforceGateway()
    await workflow.execute_workflow(output_path, gateway)

    collect.assert_awaited_once_with("postgresql://test")
    assert gateway.received_customers == customers
    assert not output_path.with_suffix(".sqlite3").exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 0


@pytest.mark.anyio
async def test_workflow_resumes_pending_customers_from_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "inactive-customers.json"
    database_path = output_path.with_suffix(".sqlite3")
    generated_at = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 26, 10, 1, tzinfo=timezone.utc)
    customers = [
        InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1)),
        InactiveCustomer(id=84, last_order_date=datetime(2026, 2, 1)),
    ]
    create_sync_database(database_path, customers, generated_at)
    save_sync_results(
        database_path,
        [
            CustomerSyncResult(
                customer_id=42,
                status=CustomerSyncStatus.SUCCEEDED,
                completed_at=completed_at,
            )
        ],
    )
    collect = AsyncMock()
    request_token = AsyncMock(return_value="test-access-token")
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", "https://example.test/token")
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(workflow, "collect_inactive_customers", collect)
    monkeypatch.setattr(workflow, "request_salesforce_access_token", request_token)

    gateway = SuccessfulSalesforceGateway()
    await workflow.execute_workflow(output_path, gateway)

    collect.assert_not_awaited()
    assert [customer.id for customer in gateway.received_customers] == [84]
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["succeeded_count"] == 2
    assert payload["failed_count"] == 0
    assert not database_path.exists()


@pytest.mark.anyio
async def test_workflow_keeps_saved_progress_after_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "inactive-customers.json"
    database_path = output_path.with_suffix(".sqlite3")
    customers = [
        InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1)),
        InactiveCustomer(id=84, last_order_date=datetime(2026, 2, 1)),
    ]
    create_sync_database(
        database_path,
        customers,
        datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
    )
    request_token = AsyncMock(return_value="test-access-token")
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", "https://example.test/token")
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(workflow, "request_salesforce_access_token", request_token)

    with pytest.raises(RuntimeError, match="Salesforce connection failed"):
        await workflow.execute_workflow(
            output_path,
            InterruptedSalesforceGateway(),
        )

    assert database_path.exists()
    assert not output_path.exists()
    assert [customer.id for customer in load_pending_customers(database_path)] == [84]
