"""All destructive fixtures are guarded by the dedicated test database name."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from app.api.integrations import order_export_dependencies as composition
from app.application.exceptions import InvalidOrderDataException
from app.infrastructure.data_mapper.order_export import PostgreSQLOrderExportDataMapper
from app.infrastructure.data_mapper.order_export.query import DETAILS_QUERY
from app.infrastructure.salesforce import SalesforceOrderAPI, SalesforceSettings, auth
from tests.test_sandbox_postgresql import _app, _client, _headers, _state
from tests.test_sandbox_postgresql import database_url as seeded_database_fixture

database_url = seeded_database_fixture


def state(url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(url) as conn:
        return conn.execute("""
            SELECT 'orders', jsonb_agg(to_jsonb(o) ORDER BY o.id) FROM public.orders AS o
            UNION ALL SELECT 'details', jsonb_agg(to_jsonb(d) ORDER BY d.id) FROM public.order_details AS d
            UNION ALL SELECT 'products', jsonb_agg(to_jsonb(p) ORDER BY p.id) FROM public.products AS p
        """).fetchall()


@pytest.mark.anyio
async def test_all_seeded_orders_read_without_writes(database_url: str) -> None:
    before = state(database_url), _state(database_url)
    reader = PostgreSQLOrderExportDataMapper(database_url)
    for reference in range(1001, 1013):
        data = await reader.get_order(reference)
        assert data is not None and data.order_number == str(reference)
        assert data.totals.net == data.totals.gross and data.totals.tax == 0
        assert data.lines and data.order_date.utcoffset() is not None
        assert all(line.line_id.isdigit() for line in data.lines)
        if reference == 1001:
            assert [line.product_reference_id for line in data.lines] == [103, 104, 101]
            assert data.lines[0].description == "Sample Order Item 5022"
    assert await reader.get_order(999999) is None
    assert await reader.order_exists(1001) and not await reader.order_exists(999999)
    assert (state(database_url), _state(database_url)) == before


@pytest.mark.anyio
async def test_real_discount_shipping_and_invoice_mapping(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "UPDATE order_details SET price=-12.00, perbox_discount=10, row_discount=20 WHERE id=5022"
        )
        conn.execute(
            "UPDATE orders SET delivery_cost=5.00,total=73.20,logistic_state='UNCONFIRMED',invoice_doc_n=123,invoice_doc_date='2026-11-06',delivery_address='Via Roma 10',delivery_city='Forli',delivery_zip_code='47121',delivery_region_id=(SELECT id FROM regions WHERE country_id=102 ORDER BY id LIMIT 1) WHERE id=1001"
        )
        product = conn.execute("SELECT id FROM products WHERE isin='ADMGST'").fetchone()
    assert product is not None
    before = state(database_url)
    data = await PostgreSQLOrderExportDataMapper(database_url).get_order(1001)
    assert data is not None and data.status == "UNCONFIRMED"
    assert data.lines[0].unit_price == 12 and data.lines[0].line_total == -12
    assert data.lines[-1].product_reference_id == product[0]
    assert data.lines[-1].line_id == "shipping-1001"
    assert data.totals.net == 61 and data.totals.tax == Decimal("12.20")
    assert data.invoice is not None and data.invoice.number == "123"
    assert (
        data.shipping_address is not None and data.shipping_address.country_code == "IT"
    )
    assert state(database_url) == before


@pytest.mark.anyio
async def test_invalid_order_can_still_send_remote_delete(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_order_export_service import Gateway

    gateway = Gateway()
    monkeypatch.setattr(composition, "_salesforce_order_gateway", gateway)
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE order_details SET qty=0 WHERE id=5022")
    before = state(database_url), _state(database_url)
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        path = "/sandbox/integrations/salesforce/orders/1001"
        assert (await client.post(path, headers=headers)).status_code == 422
        assert (await client.put(path, headers=headers)).status_code == 422
        assert (await client.delete(path, headers=headers)).status_code == 200
    assert len(gateway.events) == 1 and gateway.events[0].data is None
    assert (state(database_url), _state(database_url)) == before


@pytest.mark.anyio
async def test_shipping_missing_or_ambiguous_is_rejected(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE orders SET delivery_cost=5 WHERE id=1001")
        conn.execute("DELETE FROM products WHERE isin='ADMGST'")
    reader = PostgreSQLOrderExportDataMapper(database_url)
    with pytest.raises(InvalidOrderDataException, match="exactly one ADMGST"):
        await reader.get_order(1001)
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO products (vendor_code,isin) VALUES ('','ADMGST'),('','ADMGST')"
        )
    with pytest.raises(InvalidOrderDataException, match="exactly one ADMGST"):
        await reader.get_order(1001)


@pytest.mark.anyio
async def test_header_and_details_share_a_read_only_repeatable_snapshot(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = psycopg.AsyncCursor.execute
    reached, proceed = asyncio.Event(), asyncio.Event()
    modes: list[tuple[object, ...]] = []

    async def execute(
        cursor: Any, query: Any, params: Any = None, **kwargs: Any
    ) -> Any:
        if query == DETAILS_QUERY:
            async with cursor.connection.cursor() as probe:
                await original(
                    probe,
                    "SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation')",
                )
                modes.append(await probe.fetchone())
            reached.set()
            await proceed.wait()
        return await original(cursor, query, params, **kwargs)

    monkeypatch.setattr(psycopg.AsyncCursor, "execute", execute)
    task = asyncio.create_task(
        PostgreSQLOrderExportDataMapper(database_url).get_order(1001)
    )
    try:
        await asyncio.wait_for(reached.wait(), timeout=10)
        with psycopg.connect(database_url) as conn:
            conn.execute("UPDATE orders SET total=160 WHERE id=1001")
            conn.execute("UPDATE order_details SET price=price*2 WHERE order_id=1001")
    finally:
        proceed.set()
    result = await asyncio.wait_for(task, timeout=10)
    assert result is not None and result.totals.net == result.totals.gross == 80
    assert modes == [("on", "repeatable read")]


@pytest.mark.anyio
@pytest.mark.parametrize("remote_status", [201, 400, 404, 409, 500])
async def test_authenticated_full_flow_with_mock_remote_is_read_only(
    database_url: str, monkeypatch: pytest.MonkeyPatch, remote_status: int
) -> None:
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())
    payloads: list[dict[str, Any]] = []
    authentications = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal authentications
        if request.url.path.endswith("/token"):
            authentications += 1
            return httpx.Response(200, json={"access_token": "mock-token"})
        assert (
            request.method == "POST"
            and request.url.path == "/services/apexrest/order/sync/"
        )
        payload = json.loads(request.content)
        payloads.append(payload)
        if remote_status != 201:
            return httpx.Response(
                remote_status, json={"message": "secret remote details"}
            )
        return httpx.Response(
            201,
            json={
                "success": True,
                "eventId": payload["eventId"],
                "referenceId": str(payload["referenceId"]),
                "recordId": "801-test",
            },
        )

    settings = SalesforceSettings(
        "https://unit.my.salesforce.com/token",
        "https://unit.my.salesforce.com/customer",
        "test",
        "secret",
    )
    before = state(database_url), _state(database_url)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as remote:
        monkeypatch.setattr(
            composition,
            "_salesforce_order_gateway",
            SalesforceOrderAPI(settings, remote),
        )
        async with _client(_app(database_url)) as client:
            headers = await _headers(client, "salesforce", "romi")
            path = "/sandbox/integrations/salesforce/orders/1001"
            responses = [
                await client.request(method, path, headers=headers)
                for method in ("POST", "PUT", "DELETE")
            ]
    expected = (
        [201, 200, 200]
        if remote_status == 201
        else [404 if remote_status == 404 else 409 if remote_status == 409 else 502] * 3
    )
    assert [r.status_code for r in responses] == expected
    assert authentications == 1 and len(payloads) == 3
    assert payloads[0]["data"] == payloads[1]["data"] and "data" not in payloads[2]
    assert all("secret" not in r.text for r in responses)
    assert (state(database_url), _state(database_url)) == before


def test_sample_shipping_support_is_additive_and_idempotent(database_url: str) -> None:
    script = (
        Path(__file__).parents[1] / "docker/postgres/sandbox/order-export-support.sql"
    )
    before = state(database_url), _state(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute(script.read_text(encoding="utf-8"))
        assert conn.execute(
            "SELECT count(*) FROM products WHERE isin='ADMGST'"
        ).fetchone() == (1,)
    assert (state(database_url), _state(database_url)) == before
