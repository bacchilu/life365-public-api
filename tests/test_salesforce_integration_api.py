import os

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-with-at-least-32-bytes",
)

from app.api.integrations.routes import IntegrationCustomerData, SalesforceEventRequest
from app.main import app


@pytest.mark.anyio
async def test_receive_salesforce_event_returns_mock_success() -> None:
    event_id: str = "726c7c74-287d-44f2-b060-81fefa3d235d"
    request_body: dict[str, object] = {
        "schemaVersion": 1,
        "eventId": event_id,
        "occurredAt": "2026-09-04T10:00:00Z",
        "eventType": "customer.created",
        "data": {
            "credentials": {
                "login": "acme-italia",
                "password": "initial-customer-password",
            }
        },
    }

    request = SalesforceEventRequest.model_validate(request_body)

    assert isinstance(request.data, IntegrationCustomerData)
    assert request.data.credentials.login == "acme-italia"
    assert request.data.credentials.password == "initial-customer-password"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/integrations/salesforce/events",
            json=request_body,
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "eventId": event_id,
        "referenceId": 42,
    }
