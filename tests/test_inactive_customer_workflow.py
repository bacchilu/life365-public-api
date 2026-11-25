from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from crons import collect_inactive_customers as cron
from crons.inactive_customers import mock_salesforce, workflow
from crons.inactive_customers.model import (
    CustomerSyncResult,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.salesforce_gateway import SalesforceGateway


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", "https://example.test/token")
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(cron, "load_dotenv", lambda: None)
    return tmp_path


@pytest.mark.anyio
async def test_cron_collects_again_and_simulates_without_creating_files(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1))
    collect = AsyncMock(return_value=[customer])
    request_token = AsyncMock(return_value="test-access-token")
    monkeypatch.setattr(workflow, "collect_inactive_customers", collect)
    monkeypatch.setattr(workflow, "request_salesforce_access_token", request_token)
    monkeypatch.setattr(mock_salesforce.asyncio, "sleep", AsyncMock())

    await cron.run()
    await cron.run()

    assert collect.await_count == request_token.await_count == 2
    collect.assert_awaited_with("postgresql://test")
    output = capsys.readouterr().out
    assert output.count("Completed phase 1: 1 customers found") == 2
    assert output.count("Completed phase 2: 1 succeeded, 0 failed") == 2
    assert "Mock Salesforce sync completed; no customer data was sent" in output
    assert "test-access-token" not in output
    assert list(workspace.iterdir()) == []


@pytest.mark.anyio
async def test_empty_customer_list_skips_authentication(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(return_value=[])
    request_token = AsyncMock()
    monkeypatch.setattr(workflow, "collect_inactive_customers", collect)
    monkeypatch.setattr(workflow, "request_salesforce_access_token", request_token)

    await cron.run()

    request_token.assert_not_awaited()
    assert "No inactive customers to synchronize" in capsys.readouterr().out
    assert list(workspace.iterdir()) == []


@pytest.mark.anyio
async def test_interrupted_run_does_not_save_progress(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InterruptedSalesforceGateway(SalesforceGateway):
        async def sync_inactive_customers(
            self, customers: list[InactiveCustomer], access_token: str
        ) -> AsyncIterator[list[CustomerSyncResult]]:
            yield [
                CustomerSyncResult(
                    customer_id=customers[0].id,
                    status=CustomerSyncStatus.SUCCEEDED,
                    completed_at=datetime.now(UTC),
                )
            ]
            raise RuntimeError("Salesforce connection failed")

    collect = AsyncMock(
        return_value=[InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1))]
    )
    monkeypatch.setattr(workflow, "collect_inactive_customers", collect)
    monkeypatch.setattr(
        workflow,
        "request_salesforce_access_token",
        AsyncMock(return_value="test-token"),
    )

    with pytest.raises(RuntimeError, match="Salesforce connection failed"):
        await workflow.execute_workflow(InterruptedSalesforceGateway())

    assert list(workspace.iterdir()) == []
