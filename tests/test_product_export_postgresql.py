"""Use only the guarded automated-test database, never the seeded sandbox."""

import asyncio
import json

import httpx
import psycopg
import pytest

from app.api.integrations import product_export_dependencies as composition
from app.application.exceptions import InvalidProductDataException
from app.infrastructure.data_mapper.product_export import (
    PostgreSQLProductExportDataMapper,
)
from app.infrastructure.salesforce import SalesforceProductAPI, SalesforceSettings, auth
from tests.test_sandbox_postgresql import _app, _client, _headers, _state
from tests.test_sandbox_postgresql import database_url as seeded_database_fixture

database_url = seeded_database_fixture


def _catalog_state(database_url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as connection:
        return connection.execute("""
            SELECT 'products', jsonb_agg(to_jsonb(p) ORDER BY p.id) FROM public.products AS p
            UNION ALL SELECT 'brands', jsonb_agg(to_jsonb(b) ORDER BY b.id) FROM public.brands AS b
            UNION ALL SELECT 'images', jsonb_agg(to_jsonb(i) ORDER BY i.id) FROM public.product_images AS i
            UNION ALL SELECT 'stocks', jsonb_agg(to_jsonb(s) ORDER BY s.id) FROM public.product_stocks AS s
        """).fetchall()


@pytest.mark.anyio
async def test_seeded_catalog_exports_without_any_local_writes(
    database_url: str,
) -> None:
    before = _catalog_state(database_url), _state(database_url)
    reader = PostgreSQLProductExportDataMapper(database_url)
    data = await reader.get_product(101)
    assert data is not None and data.sku == "SAMLTD116L" and data.active is True
    assert data.ean == "0700443238779"
    assert data.category is not None and data.category.code == "1005"
    assert data.category.name == "Samsung Laserjet"
    assert data.brand is data.image_url is None
    assert data.product_url == "https://b2b.life365.eu/p/-101"
    assert await reader.product_exists(101)
    assert await reader.get_product(999999) is None
    assert not await reader.product_exists(999999)
    for identifier in range(101, 124):
        assert await reader.get_product(identifier) is not None
    assert (_catalog_state(database_url), _state(database_url)) == before


@pytest.mark.anyio
async def test_brand_and_first_image_are_resolved(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        brand = connection.execute(
            "INSERT INTO public.brands (brand_name) VALUES ('Sample Brand') RETURNING id"
        ).fetchone()
        assert brand is not None
        connection.execute(
            "UPDATE public.products SET brand_id=%s WHERE id=101", (brand[0],)
        )
        connection.execute(
            "INSERT INTO public.product_images (id,product_id,image_url) VALUES (20,101,'https://example.com/later.png'),(10,101,'https://example.com/first.png')"
        )
    data = await PostgreSQLProductExportDataMapper(database_url).get_product(101)
    assert data is not None and data.brand == "Sample Brand"
    assert data.image_url == "https://example.com/first.png"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("level_3", "level_2", "level_1", "expected"),
    [(None, 50, 1, "50"), (None, None, 1, "1"), (None, None, None, None)],
)
async def test_category_fallback_only_for_absent_levels(
    database_url: str,
    level_3: int | None,
    level_2: int | None,
    level_1: int | None,
    expected: str | None,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE public.products SET level_3=%s,level_2=%s,level_1=%s WHERE id=101",
            (level_3, level_2, level_1),
        )
    data = await PostgreSQLProductExportDataMapper(database_url).get_product(101)
    assert data is not None
    assert (data.category.code if data.category is not None else None) == expected


@pytest.mark.anyio
@pytest.mark.parametrize("column", ["level_3", "brand_id"])
async def test_unknown_reference_fails_instead_of_falling_back(
    database_url: str, column: str
) -> None:
    from psycopg import sql

    with psycopg.connect(database_url) as connection:
        connection.execute(
            sql.SQL("UPDATE public.products SET {}=999999 WHERE id=101").format(
                sql.Identifier(column)
            )
        )
    with pytest.raises(InvalidProductDataException):
        await PostgreSQLProductExportDataMapper(database_url).get_product(101)


@pytest.mark.anyio
async def test_authenticated_post_put_delete_use_real_reader_and_mock_remote(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())
    payloads: list[dict[str, object]] = []
    authentications = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal authentications
        if request.url.path.endswith("/token"):
            authentications += 1
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.method == "POST" and request.url.path.endswith("/product/sync/")
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(
            201,
            json={
                "success": True,
                "eventId": payload["eventId"],
                "referenceId": str(payload["referenceId"]),
                "recordId": "01t-test",
            },
        )

    settings = SalesforceSettings(
        "https://unit.my.salesforce.com/services/oauth2/token",
        "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
        "test-id",
        "test-secret",
    )
    before = _catalog_state(database_url), _state(database_url)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as remote:
        monkeypatch.setattr(
            composition,
            "_salesforce_product_gateway",
            SalesforceProductAPI(settings, remote),
        )
        async with _client(_app(database_url)) as client:
            headers = await _headers(client, "salesforce", "romi")
            path = "/sandbox/integrations/salesforce/products/101"
            created = await client.post(path, headers=headers)
            updated = await client.put(path, headers=headers)
            deleted = await client.delete(path, headers=headers)
            missing = await client.delete(
                path.replace("101", "999999"), headers=headers
            )
    assert [
        created.status_code,
        updated.status_code,
        deleted.status_code,
        missing.status_code,
    ] == [201, 200, 200, 404]
    assert authentications == 1 and len(payloads) == 3
    assert [p["eventType"] for p in payloads] == [
        "product.created",
        "product.updated",
        "product.deleted",
    ]
    assert payloads[0]["data"] == payloads[1]["data"] and "data" not in payloads[2]
    assert (_catalog_state(database_url), _state(database_url)) == before


@pytest.mark.anyio
async def test_incomplete_catalog_can_still_be_deactivated(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_product_export_service import Gateway

    gateway = Gateway()
    monkeypatch.setattr(composition, "_salesforce_product_gateway", gateway)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE public.products SET titles='{}'::jsonb,brand_id=999999 WHERE id=101"
        )
    before = _catalog_state(database_url), _state(database_url)
    async with _client(_app(database_url)) as client:
        headers = await _headers(client)
        path = "/sandbox/integrations/salesforce/products/101"
        assert (await client.post(path, headers=headers)).status_code == 422
        assert (await client.put(path, headers=headers)).status_code == 422
        assert (await client.delete(path, headers=headers)).status_code == 200
    assert len(gateway.events) == 1 and gateway.events[0].data is None
    assert (_catalog_state(database_url), _state(database_url)) == before


def test_support_tables_can_be_added_again_without_data_loss(database_url: str) -> None:
    from pathlib import Path

    before = _catalog_state(database_url), _state(database_url)
    script = (
        Path(__file__).parents[1] / "docker/postgres/sandbox/product-export-support.sql"
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(script.read_text(encoding="utf-8"))
    assert (_catalog_state(database_url), _state(database_url)) == before
