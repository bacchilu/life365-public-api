"""Authenticated customer events through both configured persistence backends."""

import asyncio
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi import Request
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

import app.api.integrations.routes as integration_routes
from app.api.dependencies import get_auth_service
from app.application.domain import PrincipalIdentity, PrincipalType, Role
from app.application.exceptions import AuthenticationException
from app.application.ports import CredentialsGateway
from app.application.services.auth_service import AuthService
from app.infrastructure.auth import PyJWTTokenCodec
from app.infrastructure.data_mapper.auth import InMemoryTokenSessionDataMapper
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
)
from app.main import app

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = (
    _ROOT / "tests/fixtures/integrations/salesforce/customer-sync-create-schema.sql"
)
_MIGRATION = _ROOT / "migrations/0001_customer_synchronization.sql"
_CREATE_FIXTURE = (
    _ROOT / "tests/fixtures/integrations/salesforce/customer-created-v1.json"
)
_URL = "/integrations/salesforce/events"
_TEST_TABLES = (
    "customer_synchronization_events",
    "customer_synchronization_versions",
    "customers",
    "regions",
    "countries",
    "categories",
    "agents",
    "sales_channels",
    "payment_types",
    "shop_groups",
)


class _Credentials(CredentialsGateway):
    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        if password != "test-password" or username not in ("admin", "buyer"):
            raise AuthenticationException("Invalid credentials")
        return PrincipalIdentity(
            id=1 if username == "admin" else 2,
            username=username,
            role=Role.ADMIN if username == "admin" else Role.BUYER,
            principal_type=PrincipalType.USER,
        )

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        raise AuthenticationException("Invalid credentials")


@contextmanager
def _isolated_database() -> Iterator[str]:
    url = os.environ.get("CUSTOMER_SYNC_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("Set CUSTOMER_SYNC_TEST_DATABASE_URL to an isolated database")
    database_name = conninfo_to_dict(url).get("dbname", "")
    if not database_name.startswith("life365_public_api_test_"):
        pytest.fail("Customer sync HTTP tests require a dedicated test database")
    if os.environ.get("DATABASE_URL") == url:
        pytest.fail("Test database must differ from DATABASE_URL")

    with psycopg.connect(url, autocommit=True) as conn:
        actual_name = conn.execute(sql.SQL("SELECT current_database() ")).fetchone()
        assert actual_name is not None
        if not actual_name[0].startswith("life365_public_api_test_"):
            pytest.fail("Connected database is not a customer sync test database")
        existing = conn.execute(
            sql.SQL(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = ANY(%s)"
            ),
            (list(_TEST_TABLES),),
        ).fetchall()
        if existing:
            pytest.fail("Customer sync HTTP tests require an empty test database")
        try:
            conn.execute(_SCHEMA.read_text(encoding="utf-8"))
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))
            yield url
        finally:
            conn.execute(
                sql.SQL(
                    "DROP TABLE IF EXISTS "
                    "public.customer_synchronization_events, "
                    "public.customer_synchronization_versions, "
                    "public.customers, public.regions, public.countries, "
                    "public.categories, public.agents, public.sales_channels, "
                    "public.payment_types, public.shop_groups CASCADE"
                )
            )


@dataclass(frozen=True, slots=True)
class _Backend:
    kind: integration_routes.CustomerSyncBackend
    store: InMemoryCustomerSynchronizationStore
    database_url: str | None


@pytest.fixture(params=list(integration_routes.CustomerSyncBackend))
def backend(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_Backend]:
    kind: integration_routes.CustomerSyncBackend = request.param
    store = InMemoryCustomerSynchronizationStore()
    monkeypatch.setattr(integration_routes, "CUSTOMER_SYNC_BACKEND", kind)
    monkeypatch.setattr(integration_routes, "customer_synchronization_store", store)
    monkeypatch.setenv(
        "CUSTOMER_SYNC_FINGERPRINT_SECRET", "test-customer-sync-hmac-key-32-bytes"
    )

    auth_service = AuthService(
        credentials_gateway=_Credentials(),
        token_session_gateway=InMemoryTokenSessionDataMapper(),
        token_codec=PyJWTTokenCodec("test-jwt-secret-with-at-least-32-bytes"),
    )

    async def override_auth_service() -> AuthService:
        return auth_service

    app.dependency_overrides[get_auth_service] = override_auth_service
    try:
        if kind is integration_routes.CustomerSyncBackend.MEMORY:
            yield _Backend(kind, store, None)
        else:
            with _isolated_database() as url:
                monkeypatch.setattr(integration_routes, "DATABASE_URL", url)
                yield _Backend(kind, store, url)
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://testserver",
    )


async def _headers(client: httpx.AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "username": username,
            "password": "test-password",
            "principal_type": "user",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_payload() -> dict[str, Any]:
    payload = json.loads(_CREATE_FIXTURE.read_text(encoding="utf-8"))
    payload["data"]["extensions"]["parameters"] = {
        "keep": "original",
        "nested": {"retain": 1, "remove": "old"},
    }
    return payload


def _update_payload(reference_id: int) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "eventId": str(uuid4()),
        "occurredAt": "2026-09-26T10:00:00Z",
        "resourceVersion": 2,
        "eventType": "customer.updated",
        "referenceId": reference_id,
        "data": {
            "company": {"website": None, "primaryPhone": ""},
            "commercial": {"paymentDays": 0},
            "notes": {"items": []},
            "extensions": {
                "parameters": {"nested": {"remove": None, "flag": False}}
            },
        },
    }


def _counts(backend: _Backend) -> tuple[int, int, int]:
    if backend.database_url is None:
        snapshot = backend.store.snapshot
        return (
            len(snapshot.customers),
            len(snapshot.resource_versions),
            len(snapshot.processed_events),
        )
    with psycopg.connect(backend.database_url) as conn:
        counts: list[int] = []
        for table in (
            "customers",
            "customer_synchronization_versions",
            "customer_synchronization_events",
        ):
            query = sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier("public", table)
            )
            row = conn.execute(query).fetchone()
            assert row is not None
            counts.append(row[0])
    return counts[0], counts[1], counts[2]


@pytest.mark.anyio
async def test_jwt_create_update_replay_and_version_rules(
    backend: _Backend, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _create_payload()
    with caplog.at_level(logging.INFO, logger="app.api.integrations.routes"):
        async with _client() as client:
            headers = await _headers(client, "admin")
            created = await client.post(_URL, json=payload, headers=headers)
            assert created.status_code == 200, created.text
            reference_id = created.json()["referenceId"]
            assert _counts(backend) == (1, 1, 1)

            replay = await client.post(_URL, json=payload, headers=headers)
            assert replay.status_code == 200
            assert replay.json() == created.json()
            assert _counts(backend) == (1, 1, 1)

            update = _update_payload(reference_id)
            updated = await client.post(_URL, json=update, headers=headers)
            assert updated.status_code == 200, updated.text
            assert updated.json()["referenceId"] == reference_id
            assert _counts(backend) == (1, 1, 2)

            update_replay = await client.post(_URL, json=update, headers=headers)
            assert update_replay.status_code == 200
            assert update_replay.json() == updated.json()
            assert _counts(backend) == (1, 1, 2)

            changed = json.loads(json.dumps(update))
            changed["data"]["company"]["primaryPhone"] = "changed"
            conflict = await client.post(_URL, json=changed, headers=headers)
            assert conflict.status_code == 409

            stale = json.loads(json.dumps(update))
            stale["eventId"] = str(uuid4())
            stale_response = await client.post(_URL, json=stale, headers=headers)
            assert stale_response.status_code == 409
            gap = json.loads(json.dumps(update))
            gap["eventId"] = str(uuid4())
            gap["resourceVersion"] = 4
            gap_response = await client.post(_URL, json=gap, headers=headers)
            assert gap_response.status_code == 409
            missing = _update_payload(reference_id + 999)
            missing_response = await client.post(_URL, json=missing, headers=headers)
            assert missing_response.status_code == 404

    assert _counts(backend) == (1, 1, 2)
    if backend.database_url is None:
        stored = backend.store.snapshot.customers[reference_id]
        assert stored.company.website is None
        assert stored.company.primary_phone == ""
        assert stored.commercial.payment_days == 0
        assert stored.extensions.parameters == {
            "keep": "original", "nested": {"retain": 1, "flag": False}
        }
        assert backend.store.snapshot.resource_versions[reference_id] == 2
    else:
        with psycopg.connect(backend.database_url, row_factory=dict_row) as conn:
            row = conn.execute(
                sql.SQL("SELECT * FROM public.customers WHERE id = %s"),
                (reference_id,),
            ).fetchone()
            assert row is not None
            assert row["website"] is None
            assert row["phone"] == ""
            assert row["payment_days"] == 0
            assert row["business_name"] == "ACME Italia SRL"
            assert row["registration_ip"] == "127.0.0.1"
            assert row["parameters"] == {
                "keep": "original", "nested": {"retain": 1, "flag": False}
            }
            version = conn.execute(
                sql.SQL(
                    "SELECT resource_version FROM "
                    "public.customer_synchronization_versions WHERE customer_id = %s"
                ),
                (reference_id,),
            ).fetchone()
            assert version is not None and version["resource_version"] == 2

    assert f"event_id={payload['eventId']}" in caplog.text
    assert f"reference_id={reference_id}" in caplog.text
    assert payload["data"]["credentials"]["password"] not in caplog.text


@pytest.mark.anyio
async def test_missing_token_and_non_admin_cannot_write(backend: _Backend) -> None:
    payload = _create_payload()
    async with _client() as client:
        missing = await client.post(_URL, json=payload)
        assert missing.status_code == 401
        buyer_headers = await _headers(client, "buyer")
        forbidden = await client.post(_URL, json=payload, headers=buyer_headers)
        assert forbidden.status_code == 403
    assert _counts(backend) == (0, 0, 0)


@pytest.mark.anyio
async def test_simultaneous_delivery_returns_one_committed_result(
    backend: _Backend,
) -> None:
    payload = _create_payload()
    async with _client() as client:
        headers = await _headers(client, "admin")
        first, second = await asyncio.gather(
            client.post(_URL, json=payload, headers=headers),
            client.post(_URL, json=payload, headers=headers),
        )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert _counts(backend) == (1, 1, 1)


@pytest.mark.anyio
async def test_postgresql_needs_a_stable_fingerprint_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integration_routes,
        "CUSTOMER_SYNC_BACKEND",
        integration_routes.CustomerSyncBackend.POSTGRESQL,
    )
    monkeypatch.setenv("CUSTOMER_SYNC_FINGERPRINT_SECRET", "short")
    request = Request({"type": "http", "client": ("127.0.0.1", 12345)})
    with pytest.raises(RuntimeError, match="CUSTOMER_SYNC_FINGERPRINT_SECRET"):
        await integration_routes.get_customer_synchronization_service(request)


@pytest.mark.anyio
async def test_postgresql_create_requires_ipv4_but_update_does_not(
    backend: _Backend,
) -> None:
    if backend.database_url is None:
        pytest.skip("PostgreSQL client address mapping")

    async with _client() as ipv4_client:
        headers = await _headers(ipv4_client, "admin")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("::1", 12345)),
            base_url="http://testserver",
        ) as ipv6_client:
            invalid_create = await ipv6_client.post(
                _URL, json=_create_payload(), headers=headers
            )
            assert invalid_create.status_code == 422
            assert _counts(backend) == (0, 0, 0)

            created = await ipv4_client.post(
                _URL, json=_create_payload(), headers=headers
            )
            assert created.status_code == 200
            reference_id = created.json()["referenceId"]
            updated = await ipv6_client.post(
                _URL, json=_update_payload(reference_id), headers=headers
            )
            assert updated.status_code == 200
            assert _counts(backend) == (1, 1, 2)

    with psycopg.connect(backend.database_url) as conn:
        row = conn.execute(
            sql.SQL("SELECT registration_ip FROM public.customers WHERE id = %s"),
            (reference_id,),
        ).fetchone()
        assert row == ("127.0.0.1",)


@pytest.mark.anyio
async def test_postgresql_validation_and_sql_failure_roll_back(
    backend: _Backend,
) -> None:
    if backend.database_url is None:
        pytest.skip("PostgreSQL constraint behavior")

    invalid = _create_payload()
    invalid["data"]["billingAddress"]["regionName"] = "Unknown"
    async with _client() as client:
        headers = await _headers(client, "admin")
        rejected = await client.post(_URL, json=invalid, headers=headers)
        assert rejected.status_code == 422
        assert _counts(backend) == (0, 0, 0)

        valid = _create_payload()
        created = await client.post(_URL, json=valid, headers=headers)
        assert created.status_code == 200
        reference_id = created.json()["referenceId"]
        assert _counts(backend) == (1, 1, 1)

        with psycopg.connect(backend.database_url) as conn:
            conn.execute(
                sql.SQL(
                    "ALTER TABLE public.customers ADD CONSTRAINT reject_test_name "
                    "CHECK (business_name <> 'Rejected by DB')"
                )
            )
        update = _update_payload(reference_id)
        update["data"] = {"company": {"name": "Rejected by DB"}}
        failed = await client.post(_URL, json=update, headers=headers)
        assert failed.status_code == 503
        assert _counts(backend) == (1, 1, 1)

    with psycopg.connect(backend.database_url) as conn:
        row = conn.execute(
            sql.SQL("SELECT business_name FROM public.customers WHERE id = %s"),
            (reference_id,),
        ).fetchone()
        assert row == ("ACME Italia SRL",)
