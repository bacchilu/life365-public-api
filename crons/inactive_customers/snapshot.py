import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from crons.inactive_customers.model import (
    CustomerSyncRecord,
    CustomerSyncRun,
    CustomerSyncStatus,
)


def build_report_paths(
    base_output_path: Path,
    completed_at: datetime,
) -> tuple[Path, Path]:
    timestamp: str = completed_at.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    timestamped_path = base_output_path.with_name(
        f"{base_output_path.stem}-{timestamp}{base_output_path.suffix}"
    )
    latest_path = base_output_path.with_name(
        f"{base_output_path.stem}-latest{base_output_path.suffix}"
    )
    return timestamped_path, latest_path


def write_inactive_customers(
    output_path: Path,
    run: CustomerSyncRun,
    records: list[CustomerSyncRecord],
) -> None:
    payload: dict[str, object] = {
        "generated_at": run.generated_at.isoformat(),
        "completed_at": (
            run.completed_at.isoformat() if run.completed_at is not None else None
        ),
        "customer_count": len(records),
        "succeeded_count": sum(
            record.status is CustomerSyncStatus.SUCCEEDED for record in records
        ),
        "failed_count": sum(
            record.status is CustomerSyncStatus.FAILED for record in records
        ),
        "customers": [_customer_payload(record) for record in records],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            json.dump(payload, output_file, indent=2)
            output_file.write("\n")
            output_file.flush()
            os.fsync(output_file.fileno())

        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _customer_payload(record: CustomerSyncRecord) -> dict[str, object]:
    sync: dict[str, object] = {
        "status": record.status.value,
        "attempt_count": record.attempt_count,
        "completed_at": (
            record.completed_at.isoformat()
            if record.completed_at is not None
            else None
        ),
    }
    if record.http_status is not None:
        sync["http_status"] = record.http_status
    if record.error is not None:
        sync["error"] = record.error

    return {
        "id": record.customer.id,
        "last_order_date": record.customer.last_order_date.isoformat(),
        "sync": sync,
    }
