import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from crons.inactive_customers.database import collect_inactive_customers
from crons.inactive_customers.locking import acquire_job_lock
from crons.inactive_customers.model import InactiveCustomer
from crons.inactive_customers.snapshot import write_inactive_customers

DEFAULT_OUTPUT_PATH: Path = Path("data/inactive-customers.json")


def main() -> None:
    load_dotenv()
    connection_string: str | None = os.environ.get("DATABASE_URL")
    output_path = Path(
        os.environ.get("INACTIVE_CUSTOMERS_OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH))
    )

    if connection_string is None:
        raise RuntimeError("DATABASE_URL is not configured")

    lock_path = output_path.with_suffix(".lock")
    with acquire_job_lock(lock_path) as acquired:
        if not acquired:
            print(
                "Inactive customer collection is already running; "
                "skipping this execution",
                flush=True,
            )
            return

        print("Starting inactive customer collection", flush=True)
        customers: list[InactiveCustomer] = collect_inactive_customers(
            connection_string
        )
        write_inactive_customers(
            output_path,
            customers,
            generated_at=datetime.now(timezone.utc),
        )

        print(
            "Inactive customer collection completed successfully: "
            f"{len(customers)} customers written to {output_path}",
            flush=True,
        )


if __name__ == "__main__":
    main()
