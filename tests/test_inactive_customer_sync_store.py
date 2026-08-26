from datetime import datetime, timezone
from pathlib import Path

import pytest

from crons.inactive_customers.model import (
    CustomerSyncResult,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.sync_store import (
    complete_sync_run,
    create_sync_database,
    load_pending_customers,
    load_sync_run,
    remove_sync_database,
    save_sync_results,
)


def test_sync_database_tracks_results_and_completion(tmp_path: Path) -> None:
    database_path = tmp_path / "inactive-customers.sqlite3"
    generated_at = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 26, 10, 5, tzinfo=timezone.utc)
    customers = [
        InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1)),
        InactiveCustomer(id=84, last_order_date=datetime(2026, 2, 1)),
    ]
    create_sync_database(database_path, customers, generated_at)

    save_sync_results(
        database_path,
        [
            CustomerSyncResult(
                customer_id=42,
                status=CustomerSyncStatus.SUCCEEDED,
                completed_at=completed_at,
            ),
            CustomerSyncResult(
                customer_id=84,
                status=CustomerSyncStatus.FAILED,
                completed_at=completed_at,
                http_status=400,
                error="Invalid customer",
            ),
        ],
    )
    complete_sync_run(database_path, completed_at)

    run, records = load_sync_run(database_path)
    assert load_pending_customers(database_path) == []
    assert run.generated_at == generated_at
    assert run.completed_at == completed_at
    assert [record.status for record in records] == [
        CustomerSyncStatus.SUCCEEDED,
        CustomerSyncStatus.FAILED,
    ]
    assert records[1].http_status == 400
    assert records[1].error == "Invalid customer"

    remove_sync_database(database_path)
    assert not database_path.exists()


def test_sync_run_cannot_complete_with_pending_customers(tmp_path: Path) -> None:
    database_path = tmp_path / "inactive-customers.sqlite3"
    create_sync_database(
        database_path,
        [InactiveCustomer(id=42, last_order_date=datetime(2026, 1, 1))],
        datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(RuntimeError, match="still has 1 pending customer"):
        complete_sync_run(
            database_path,
            datetime(2026, 8, 26, 10, 5, tzinfo=timezone.utc),
        )
