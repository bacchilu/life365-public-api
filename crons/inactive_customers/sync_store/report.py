import sqlite3
from datetime import datetime
from pathlib import Path

from crons.inactive_customers.model import (
    CustomerSyncRecord,
    CustomerSyncRun,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.sync_store.schema import validate_schema


def load_sync_run(
    database_path: Path,
) -> tuple[CustomerSyncRun, list[CustomerSyncRecord]]:
    with sqlite3.connect(database_path) as connection:
        validate_schema(connection)
        run_row = connection.execute(
            "SELECT generated_at, completed_at FROM sync_run WHERE id = 1"
        ).fetchone()
        if run_row is None:
            raise RuntimeError("Sync database does not contain run metadata")
        rows = connection.execute(
            """
            SELECT customer_id, last_order_date, status, attempt_count,
                   completed_at, http_status, error
            FROM sync_items
            ORDER BY last_order_date, customer_id
            """
        ).fetchall()

    run = CustomerSyncRun(
        generated_at=datetime.fromisoformat(run_row[0]),
        completed_at=(datetime.fromisoformat(run_row[1]) if run_row[1] else None),
    )
    records = [
        CustomerSyncRecord(
            customer=InactiveCustomer(row[0], datetime.fromisoformat(row[1])),
            status=CustomerSyncStatus(row[2]),
            attempt_count=row[3],
            completed_at=datetime.fromisoformat(row[4]) if row[4] else None,
            http_status=row[5],
            error=row[6],
        )
        for row in rows
    ]
    return run, records
