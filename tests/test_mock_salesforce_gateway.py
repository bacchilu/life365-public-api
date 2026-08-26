from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from crons.inactive_customers import mock_salesforce
from crons.inactive_customers.mock_salesforce import MockSalesforceGateway
from crons.inactive_customers.model import InactiveCustomer


@pytest.mark.anyio
async def test_mock_salesforce_gateway_reports_mock_sync(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(mock_salesforce.random, "randint", lambda start, end: 12)
    monkeypatch.setattr(mock_salesforce.asyncio, "sleep", sleep)
    gateway = MockSalesforceGateway()
    customers = [
        InactiveCustomer(
            id=42,
            last_order_date=datetime(2026, 1, 1),
        )
    ]

    await gateway.sync_inactive_customers(customers, "test-access-token")

    output = capsys.readouterr().out
    assert "Starting mock Salesforce sync for 1 customers" in output
    assert "Mock Salesforce sync will take 12 seconds" in output
    assert "Mock Salesforce sync completed; no customer data was sent" in output
    assert "test-access-token" not in output
    sleep.assert_awaited_once_with(12)
