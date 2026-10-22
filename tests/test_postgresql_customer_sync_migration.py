"""Verify the destructive history reset only on an isolated test database."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_RESET = _MIGRATIONS / "0002_remove_customer_resource_versions.sql"


@pytest.fixture
def database() -> Iterator[psycopg.Connection]:
    url = os.environ.get("CUSTOMER_SYNC_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CUSTOMER_SYNC_TEST_DATABASE_URL to an isolated database")
    if (
        not conninfo_to_dict(url)
        .get("dbname", "")
        .startswith("life365_public_api_test_")
    ):
        pytest.fail("Migration tests require a dedicated test database")
    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.info.dbname.startswith("life365_public_api_test_")
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        if tables:
            pytest.fail("Migration tests require an empty test database")
        try:
            conn.execute(
                "CREATE TABLE public.customers (id integer PRIMARY KEY, business_name text)"
            )
            conn.execute(
                "INSERT INTO public.customers VALUES (42, 'Keep this customer')"
            )
            conn.execute(
                (_MIGRATIONS / "0001_customer_synchronization.sql").read_text(
                    encoding="utf-8"
                )
            )
            conn.execute(
                "INSERT INTO public.customer_synchronization_versions (customer_id, resource_version) VALUES (42, 1)"
            )
            conn.execute(
                "INSERT INTO public.customer_synchronization_events "
                "(event_id, event_fingerprint, schema_version, event_type, occurred_at, resource_version, result_success, result_reference_id) "
                "VALUES (%s, %s, 1, 'customer.created', now(), 1, true, 42)",
                (UUID(int=1), b"x" * 32),
            )
            yield conn
        finally:
            conn.execute("ROLLBACK")
            conn.execute("DROP VIEW IF EXISTS public.test_version_dependency")
            conn.execute(
                "DROP TABLE IF EXISTS public.customer_synchronization_events, public.customer_synchronization_versions, public.customers"
            )


def test_migration_clears_only_history_and_preserves_constraints(
    database: psycopg.Connection,
) -> None:
    before = database.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'public.customer_synchronization_events'::regclass "
        "AND pg_get_constraintdef(oid) NOT LIKE '%resource_version%' ORDER BY conname"
    ).fetchall()
    database.execute(_RESET.read_text(encoding="utf-8"))
    assert database.execute("SELECT * FROM public.customers").fetchall() == [
        (42, "Keep this customer")
    ]
    assert database.execute(
        "SELECT count(*) FROM public.customer_synchronization_events"
    ).fetchone() == (0,)
    assert database.execute(
        "SELECT to_regclass('public.customer_synchronization_versions')"
    ).fetchone() == (None,)
    assert (
        database.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'customer_synchronization_events' AND column_name = 'resource_version'"
        ).fetchall()
        == []
    )
    after = database.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'public.customer_synchronization_events'::regclass ORDER BY conname"
    ).fetchall()
    assert after == before


def test_migration_failure_rolls_back_history_deletion(
    database: psycopg.Connection,
) -> None:
    database.execute(
        "CREATE VIEW public.test_version_dependency AS SELECT customer_id FROM public.customer_synchronization_versions"
    )
    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        database.execute(_RESET.read_text(encoding="utf-8"))
    database.execute("ROLLBACK")
    assert database.execute(
        "SELECT count(*) FROM public.customer_synchronization_events"
    ).fetchone() == (1,)
    assert database.execute(
        "SELECT resource_version FROM public.customer_synchronization_versions"
    ).fetchone() == (1,)
