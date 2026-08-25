import fcntl
import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import TupleRow

QUALIFYING_LOGISTIC_STATES: tuple[str, ...] = (
    "CONFIRMED",
    "DELIVERED",
    "UNDELIVERABLE",
)
DEFAULT_OUTPUT_PATH = Path("data/inactive-customers.json")

INACTIVE_CUSTOMERS_QUERY = sql.SQL(
    """
    WITH latest_qualifying_orders AS (
        SELECT
            customer_id,
            MAX(order_date) AS last_order_date
        FROM public.orders
        WHERE customer_id IS NOT NULL
          AND logistic_state = ANY(%(states)s)
        GROUP BY customer_id
    )
    SELECT
        c.id,
        latest.last_order_date
    FROM public.customers AS c
    INNER JOIN latest_qualifying_orders AS latest
        ON latest.customer_id = c.id
    WHERE latest.last_order_date < CURRENT_TIMESTAMP - INTERVAL '90 days'
    ORDER BY latest.last_order_date, c.id
    """
)


@dataclass(frozen=True, slots=True)
class InactiveCustomer:
    id: int
    last_order_date: datetime


@contextmanager
def acquire_job_lock(lock_path: Path) -> Generator[bool]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def collect_inactive_customers(connection_string: str) -> list[InactiveCustomer]:
    with (
        psycopg.connect(connection_string) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            INACTIVE_CUSTOMERS_QUERY,
            {"states": list(QUALIFYING_LOGISTIC_STATES)},
        )
        rows: list[TupleRow] = cursor.fetchall()

    return [InactiveCustomer(id=row[0], last_order_date=row[1]) for row in rows]


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
