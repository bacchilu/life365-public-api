import json
from datetime import datetime, timezone
from pathlib import Path

from crons.inactive_customers.locking import acquire_job_lock
from crons.inactive_customers.model import (
    CustomerSyncRecord,
    CustomerSyncRun,
    CustomerSyncStatus,
    InactiveCustomer,
)
from crons.inactive_customers.snapshot import (
    build_report_paths,
    write_inactive_customers,
)


def test_job_lock_prevents_overlapping_execution(tmp_path: Path) -> None:
    lock_path = tmp_path / "inactive-customers.lock"

    with acquire_job_lock(lock_path) as first_acquired:
        assert first_acquired is True

        with acquire_job_lock(lock_path) as second_acquired:
            assert second_acquired is False

    with acquire_job_lock(lock_path) as acquired_after_release:
        assert acquired_after_release is True


def test_write_inactive_customers_creates_json_snapshot(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "inactive-customers.json"
    generated_at = datetime(2026, 8, 24, 10, 30, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 24, 10, 45, tzinfo=timezone.utc)
    records = [
        CustomerSyncRecord(
            customer=InactiveCustomer(
                id=42,
                last_order_date=datetime(2026, 5, 1, 9, 15),
            ),
            status=CustomerSyncStatus.SUCCEEDED,
            attempt_count=1,
            completed_at=datetime(2026, 8, 24, 10, 40, tzinfo=timezone.utc),
            http_status=None,
            error=None,
        ),
        CustomerSyncRecord(
            customer=InactiveCustomer(
                id=84,
                last_order_date=datetime(2025, 12, 12, 16, 45),
            ),
            status=CustomerSyncStatus.FAILED,
            attempt_count=3,
            completed_at=datetime(2026, 8, 24, 10, 42, tzinfo=timezone.utc),
            http_status=400,
            error="Customer data is invalid",
        ),
    ]

    write_inactive_customers(
        output_path,
        CustomerSyncRun(generated_at=generated_at, completed_at=completed_at),
        records,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "generated_at": "2026-08-24T10:30:00+00:00",
        "completed_at": "2026-08-24T10:45:00+00:00",
        "customer_count": 2,
        "succeeded_count": 1,
        "failed_count": 1,
        "customers": [
            {
                "id": 42,
                "last_order_date": "2026-05-01T09:15:00",
                "sync": {
                    "status": "succeeded",
                    "attempt_count": 1,
                    "completed_at": "2026-08-24T10:40:00+00:00",
                },
            },
            {
                "id": 84,
                "last_order_date": "2025-12-12T16:45:00",
                "sync": {
                    "status": "failed",
                    "attempt_count": 3,
                    "completed_at": "2026-08-24T10:42:00+00:00",
                    "http_status": 400,
                    "error": "Customer data is invalid",
                },
            },
        ],
    }
    assert list(output_path.parent.glob("*.tmp")) == []


def test_build_report_paths_uses_utc_completion_timestamp() -> None:
    report_path, latest_path = build_report_paths(
        Path("data/inactive-customers.json"),
        datetime(2026, 8, 26, 12, 30, 45, tzinfo=timezone.utc),
    )

    assert report_path == Path(
        "data/inactive-customers-20260826T123045Z.json"
    )
    assert latest_path == Path("data/inactive-customers-latest.json")
