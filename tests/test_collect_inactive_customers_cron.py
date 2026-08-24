import json
from datetime import datetime, timezone
from pathlib import Path

from crons.collect_inactive_customers import (
    InactiveCustomer,
    write_inactive_customers,
)


def test_write_inactive_customers_creates_json_snapshot(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "inactive-customers.json"
    generated_at = datetime(2026, 8, 24, 10, 30, tzinfo=timezone.utc)
    customers = [
        InactiveCustomer(
            id=42,
            last_order_date=datetime(2026, 5, 1, 9, 15),
        ),
        InactiveCustomer(
            id=84,
            last_order_date=datetime(2025, 12, 12, 16, 45),
        ),
    ]

    write_inactive_customers(output_path, customers, generated_at)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "generated_at": "2026-08-24T10:30:00+00:00",
        "customer_count": 2,
        "customers": [
            {"id": 42, "last_order_date": "2026-05-01T09:15:00"},
            {"id": 84, "last_order_date": "2025-12-12T16:45:00"},
        ],
    }
    assert list(output_path.parent.glob("*.tmp")) == []
