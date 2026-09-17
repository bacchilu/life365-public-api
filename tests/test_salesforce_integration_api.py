import json
import os
from pathlib import Path

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-with-at-least-32-bytes",
)

import app.api.integrations.routes as integration_routes
from app.api.integrations.routes import SalesforceEventRequest
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as ApiIntegrationCustomerData,
)
from app.application.dtos.customer_integration.events import (
    CustomerSynchronizationResult,
)
from app.main import app

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_EVENT_ADAPTER = TypeAdapter(SalesforceEventRequest)


def test_salesforce_event_rejects_customer_deletion() -> None:
    with pytest.raises(ValidationError):
        _EVENT_ADAPTER.validate_python(
            {
                "schemaVersion": 1,
                "eventId": "726c7c74-287d-44f2-b060-81fefa3d235d",
                "occurredAt": "2026-09-04T10:00:00Z",
                "eventType": "customer.deleted",
                "referenceId": 42,
            }
        )


@pytest.mark.anyio
async def test_receive_salesforce_event_returns_mock_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_body: dict[str, object] = json.loads(
        _FIXTURE_PATH.read_text(encoding="utf-8")
    )

    class FakeCustomerSynchronizationService:
        async def synchronize_customer(
            self, _event: object
        ) -> CustomerSynchronizationResult:
            return CustomerSynchronizationResult(success=True, reference_id=42)

    monkeypatch.setattr(
        integration_routes,
        "customer_synchronization_service",
        FakeCustomerSynchronizationService(),
    )

    request = _EVENT_ADAPTER.validate_python(request_body)

    assert isinstance(request.data, ApiIntegrationCustomerData)
    assert request.data.credentials.login == "acme-italia"
    assert request.data.company.name == "ACME Italia SRL"

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
        "eventId": request_body["eventId"],
        "referenceId": 42,
    }
