"""Check Flow 2 with the guarded, dedicated PostgreSQL test database."""

import psycopg
import pytest

from app.api.integrations import customer_reactivation_dependencies as composition
from app.application.dtos.customer_reactivation import (
    CustomerReactivationReceipt,
    CustomerReactivationRequest,
)
from tests.test_sandbox_postgresql import _app, _client, _headers, _state
from tests.test_sandbox_postgresql import database_url as seeded_database_fixture

database_url = seeded_database_fixture


@pytest.mark.anyio
async def test_reactivation_checks_last_qualifying_order_without_writes(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[CustomerReactivationRequest] = []

    class Gateway:
        async def send_customer_reactivation(
            self, request: CustomerReactivationRequest
        ) -> CustomerReactivationReceipt:
            sent.append(request)
            return CustomerReactivationReceipt(("r1", "r2", "r3", "r4"))

    monkeypatch.setattr(composition, "SalesforceMarketingAPI", Gateway)
    path = "/sandbox/integrations/salesforce/customers/{}/marketing/reactivation"
    body = {"related_product": ["101", "102", "103", "104"], "related_product2": []}
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        assert (
            await client.post(path.format(999999), headers=headers, json=body)
        ).status_code == 404
        for logistic_state, age, expected in (
            ("UNCONFIRMED", 120, 409),
            ("CONFIRMED", 89, 409),
            ("UNDELIVERABLE", 91, 201),
        ):
            with psycopg.connect(database_url) as conn:
                conn.execute(
                    """
                    UPDATE public.orders
                    SET logistic_state = %s,
                        order_date = CURRENT_TIMESTAMP - %s * INTERVAL '1 day'
                    WHERE customer_id = 4
                    """,
                    (logistic_state, age),
                )
            before = _state(database_url)
            response = await client.post(path.format(4), headers=headers, json=body)
            assert response.status_code == expected
            assert _state(database_url) == before
        with psycopg.connect(database_url) as conn:
            conn.execute("""
                UPDATE public.orders
                SET customer_id = 4, logistic_state = 'DELIVERED',
                    order_date = CURRENT_TIMESTAMP - INTERVAL '1 day'
                WHERE id = 1002
                """)
        assert (
            await client.post(path.format(4), headers=headers, json=body)
        ).status_code == 409
    assert sent == [CustomerReactivationRequest(4, (101, 102, 103, 104), ())]
