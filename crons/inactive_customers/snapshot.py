import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from crons.inactive_customers.model import InactiveCustomer


def write_inactive_customers(
    output_path: Path,
    customers: list[InactiveCustomer],
    generated_at: datetime,
) -> None:
    payload: dict[str, object] = {
        "generated_at": generated_at.isoformat(),
        "customer_count": len(customers),
        "customers": [
            {
                "id": customer.id,
                "last_order_date": customer.last_order_date.isoformat(),
            }
            for customer in customers
        ],
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
