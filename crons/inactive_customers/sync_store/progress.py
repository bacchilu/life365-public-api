import sqlite3
from datetime import datetime
from pathlib import Path

from crons.inactive_customers.model import CustomerSyncResult, InactiveCustomer
from crons.inactive_customers.sync_store.schema import (
    UPDATE_RESULT,
    validate_schema,
)


def load_pending_customers(database_path: Path) -> list[InactiveCustomer]:
    with sqlite3.connect(database_path) as connection:
        validate_schema(connection)
        rows = connection.execute(
            """
            SELECT customer_id, last_order_date
            FROM sync_items
            WHERE status = 'pending'
            ORDER BY last_order_date, customer_id
            """
        ).fetchall()

    return [
        InactiveCustomer(id=row[0], last_order_date=datetime.fromisoformat(row[1]))
        for row in rows
    ]


def save_sync_results(
    database_path: Path,
    results: list[CustomerSyncResult],
) -> None:
    with sqlite3.connect(database_path) as connection:
        validate_schema(connection)
        for result in results:
            cursor = connection.execute(
                UPDATE_RESULT,
                {
                    "customer_id": result.customer_id,
                    "status": result.status.value,
                    "completed_at": result.completed_at.isoformat(),
                    "http_status": result.http_status,
                    "error": result.error,
                },
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Customer {result.customer_id} is not pending in the sync run"
                )
