"""Exercise sandbox wiring with its bundled seed only in the dedicated test DB."""

import asyncio
import json
import os
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.api.application import create_api_application
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.settings import SandboxSettings

_ROOT = Path(__file__).resolve().parents[1]
_DATABASE = "life365_public_api_test_customer_sync"
_URL = "/sandbox/integrations/salesforce/events"
_TABLES = (
    "customer_synchronization_events",
    "customer_synchronization_versions",
    "order_details",
    "orders",
    "product_stocks",
    "products",
    "customers",
    "users",
    "shop_groups",
    "payment_types",
    "sales_channels",
    "agents",
    "categories",
    "regions",
    "countries",
)


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = os.environ.get("CUSTOMER_SYNC_TEST_DATABASE_URL")
    if url is None:
        pytest.skip(
            "Set CUSTOMER_SYNC_TEST_DATABASE_URL to the dedicated test database"
        )
    if conninfo_to_dict(url).get("dbname") != _DATABASE or url == os.environ.get(
        "DATABASE_URL"
    ):
        pytest.fail("Sandbox HTTP tests require the dedicated automated-test database")
    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.execute("SELECT current_database()").fetchone() == (_DATABASE,)
        if conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall():
            pytest.fail("Sandbox HTTP fixtures require an empty test database")
        original_connect = psycopg.AsyncConnection.connect

        async def guarded_connect(conninfo: str = "", **kwargs: Any) -> Any:
            assert conninfo_to_dict(conninfo).get("dbname") == _DATABASE
            return await original_connect(conninfo, **kwargs)

        monkeypatch.setattr(psycopg.AsyncConnection, "connect", guarded_connect)
        try:
            for path in (
                "docker/postgres/sandbox/schema.sql",
                "docker/postgres/sandbox/data.sql",
                "migrations/0001_customer_synchronization.sql",
                "migrations/0002_remove_customer_resource_versions.sql",
            ):
                conn.execute((_ROOT / path).read_text(encoding="utf-8"))
            yield url
        finally:
            conn.execute(
                sql.SQL("DROP TABLE IF EXISTS {}").format(
                    sql.SQL(", ").join(
                        sql.Identifier("public", table) for table in _TABLES
                    )
                )
            )


def _app(url: str) -> FastAPI:
    app = create_api_application("Existing API")
    app.mount(
        "/sandbox",
        create_sandbox_application(
            SandboxSettings(
                url,
                "sandbox-jwt-secret-for-tests-32-bytes",
                b"sandbox-event-secret-for-tests-32-bytes",
            )
        ),
    )
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
        base_url="http://testserver",
    )


async def _headers(
    client: httpx.AsyncClient,
    username: str = "sandbox-admin",
    password: str = "sandbox-admin",
    principal: str = "user",
) -> dict[str, str]:
    response = await client.post(
        "/sandbox/auth/login",
        json={"username": username, "password": password, "principal_type": principal},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create() -> dict[str, Any]:
    payload = json.loads(
        (
            _ROOT / "tests/fixtures/integrations/salesforce/customer-created-v1.json"
        ).read_text(encoding="utf-8")
    )
    payload["eventId"] = str(uuid4())
    payload["data"]["extensions"]["parameters"] = {
        "keep": "original",
        "nested": {"keep": 1, "remove": "old"},
    }
    return payload


def _update(reference_id: int, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "eventId": str(uuid4()),
        "occurredAt": "2020-01-01T00:00:00Z",
        "eventType": "customer.updated",
        "referenceId": reference_id,
        "data": data,
    }


def _state(url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        customers = conn.execute(
            "SELECT * FROM public.customers ORDER BY id"
        ).fetchall()
        events = conn.execute(
            "SELECT * FROM public.customer_synchronization_events ORDER BY event_id"
        ).fetchall()
        return customers, events


@pytest.mark.anyio
async def test_seeded_reads_authentication_and_authorization(database_url: str) -> None:
    before = _state(database_url)
    assert len(before[0]) == 7 and before[1] == []
    async with _client(_app(database_url)) as client:
        admin = await _headers(client)
        for path in ("customers", "orders", "products"):
            response = await client.get(f"/sandbox/{path}", headers=admin)
            assert response.status_code == 200, response.text
            assert response.json()
        assert (await client.get("/sandbox/health")).json() == {
            "status": "ok",
            "db": "ok",
        }
        for username, password, principal in (
            ("sandbox-buyer", "sandbox-buyer", "user"),
            ("sandbox-customer-1", "sandbox-customer", "customer"),
        ):
            headers = await _headers(client, username, password, principal)
            assert (
                await client.post(_URL, json=_create(), headers=headers)
            ).status_code == 403
        assert (await client.post(_URL, json=_create())).status_code == 401
        salesforce = await _headers(client, "salesforce", "romi")
        assert (
            await client.get("/sandbox/customers", headers=salesforce)
        ).status_code == 200
        assert (
            await client.get("/sandbox/products/recommend?order_id=1", headers=admin)
        ).status_code == 501
    assert _state(database_url) == before


@pytest.mark.anyio
async def test_create_update_replay_conflicts_and_restart(database_url: str) -> None:
    app = _app(database_url)
    payload = _create()
    async with _client(app) as client:
        headers = await _headers(client)
        created = await client.post(_URL, json=payload, headers=headers)
        assert created.status_code == 200, created.text
        reference_id = created.json()["referenceId"]
        assert created.json() == {
            "success": True,
            "eventId": payload["eventId"],
            "referenceId": reference_id,
        }
        assert (
            await client.post(_URL, json=payload, headers=headers)
        ).json() == created.json()
        changed = deepcopy(payload)
        changed["data"]["company"]["name"] = "Changed content"
        assert (
            await client.post(_URL, json=changed, headers=headers)
        ).status_code == 409
        update = _update(
            reference_id,
            {
                "company": {"website": None, "primaryPhone": ""},
                "commercial": {"paymentDays": 0, "preferredCategories": []},
                "primaryContact": {"additionalEmails": []},
                "operationalSettings": {"prepaidReturns": False},
                "extensions": {
                    "parameters": {"nested": {"remove": None, "flag": False}}
                },
            },
        )
        updated = await client.post(_URL, json=update, headers=headers)
        assert updated.status_code == 200, updated.text
        assert (
            await client.post(_URL, json=update, headers=headers)
        ).json() == updated.json()
        for body in (payload, update):
            assert (
                await client.post(
                    _URL, json={**body, "resourceVersion": 1}, headers=headers
                )
            ).status_code == 422
        assert (
            await client.post(
                _URL,
                json=_update(999999, {"company": {"name": "Missing"}}),
                headers=headers,
            )
        ).status_code == 404
        bad_reference = _update(
            reference_id,
            {
                "company": {"name": "Must roll back"},
                "billingAddress": {"regionName": "Unknown region"},
            },
        )
        before = _state(database_url)
        assert (
            await client.post(_URL, json=bad_reference, headers=headers)
        ).status_code == 422
        assert _state(database_url) == before
    customers, events = _state(database_url)
    assert len(customers) == 8 and len(events) == 2
    row = next(item for item in customers if item["id"] == reference_id)
    assert row["business_name"] == payload["data"]["company"]["name"]
    assert row["phone"] == "" and row["website"] is None
    assert row["payment_days"] == 0 and row["rma_prepaid"] is False
    assert row["preferred_categories"] == [] and row["additional_emails"] == []
    assert row["registration_ip"] == "127.0.0.1"
    assert row["parameters"] == {
        "keep": "original",
        "nested": {"keep": 1, "flag": False},
    }
    assert payload["data"]["credentials"]["password"] not in repr(events)
    async with _client(_app(database_url)) as restarted:
        headers = await _headers(restarted)
        assert (
            await restarted.post(_URL, json=payload, headers=headers)
        ).json() == created.json()
    assert _state(database_url) == (customers, events)


@pytest.mark.anyio
async def test_duplicates_and_concurrent_json_merges(database_url: str) -> None:
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        payload = _create()
        first, second = await asyncio.gather(
            *(client.post(_URL, json=payload, headers=headers) for _ in range(2))
        )
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        reference_id = first.json()["referenceId"]
        assert len(_state(database_url)[1]) == 1
        patches = [
            _update(reference_id, {"extensions": {"parameters": {name: True}}})
            for name in ("first", "second")
        ]
        results = await asyncio.gather(
            *(client.post(_URL, json=patch, headers=headers) for patch in patches)
        )
        assert [result.status_code for result in results] == [200, 200]
        customers, events = _state(database_url)
        row = next(item for item in customers if item["id"] == reference_id)
        assert row["parameters"] == {
            **payload["data"]["extensions"]["parameters"],
            "first": True,
            "second": True,
        }
        assert len(customers) == 8 and len(events) == 3


@pytest.mark.anyio
async def test_seeded_customer_update_without_prior_event(database_url: str) -> None:
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        response = await client.post(
            _URL,
            json=_update(1, {"company": {"name": "Updated seeded customer"}}),
            headers=headers,
        )
        assert response.status_code == 200, response.text
    customers, events = _state(database_url)
    assert customers[0]["business_name"] == "Updated seeded customer"
    assert customers[0]["address_street"] == "Sample Street 1"
    assert len(customers) == 7 and len(events) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("create", [True, False])
async def test_event_completion_failure_rolls_back_customer_changes(
    database_url: str, create: bool
) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "ALTER TABLE public.customer_synchronization_events ADD CONSTRAINT test_reject_completion CHECK (false) NOT VALID"
        )
    before = _state(database_url)
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        payload = (
            _create()
            if create
            else _update(1, {"company": {"name": "Never committed"}})
        )
        response = await client.post(_URL, json=payload, headers=headers)
        assert response.status_code == 503, response.text
    assert _state(database_url) == before
