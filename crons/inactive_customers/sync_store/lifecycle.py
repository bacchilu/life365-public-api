import sqlite3
from datetime import datetime
from pathlib import Path

from crons.inactive_customers.model import InactiveCustomer
from crons.inactive_customers.sync_store.schema import (
    CREATE_SCHEMA,
    INSERT_CUSTOMER,
    INSERT_RUN,
    SCHEMA_VERSION,
    validate_schema,
)


def create_sync_database(
    database_path: Path,
    customers: list[InactiveCustomer],
    generated_at: datetime,
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        raise FileExistsError(f"Sync database already exists: {database_path}")

    try:
        with sqlite3.connect(database_path) as connection:
            connection.executescript(CREATE_SCHEMA)
            connection.execute(
                INSERT_RUN,
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": generated_at.isoformat(),
                },
            )
            connection.executemany(
                INSERT_CUSTOMER,
                (
                    {
                        "customer_id": customer.id,
                        "last_order_date": customer.last_order_date.isoformat(),
                    }
                    for customer in customers
                ),
            )
    except Exception:
        remove_sync_database(database_path)
        raise


def complete_sync_run(database_path: Path, completed_at: datetime) -> None:
    with sqlite3.connect(database_path) as connection:
        validate_schema(connection)
        pending_row = connection.execute(
            "SELECT COUNT(*) FROM sync_items WHERE status = 'pending'"
        ).fetchone()
        if pending_row is None:
            raise RuntimeError("Sync database does not contain customer state")
        pending_count: int = pending_row[0]
        if pending_count:
            raise RuntimeError(f"Sync run still has {pending_count} pending customers")
        connection.execute(
            "UPDATE sync_run SET completed_at = COALESCE(completed_at, :completed_at)",
            {"completed_at": completed_at.isoformat()},
        )


def remove_sync_database(database_path: Path) -> None:
    for path in (
        database_path,
        Path(f"{database_path}-journal"),
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        path.unlink(missing_ok=True)
