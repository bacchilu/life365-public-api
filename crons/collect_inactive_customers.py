import os
from dataclasses import dataclass
from datetime import datetime

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import TupleRow

QUALIFYING_LOGISTIC_STATES: tuple[str, ...] = (
    "CONFIRMED",
    "DELIVERED",
    "UNDELIVERABLE",
)

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


def main() -> None:
    load_dotenv()
    connection_string: str | None = os.environ.get("DATABASE_URL")

    if connection_string is None:
        raise RuntimeError("DATABASE_URL is not configured")

    customers: list[InactiveCustomer] = collect_inactive_customers(connection_string)

    print(f"Inactive customers: {len(customers)}", flush=True)
    for customer in customers:
        print(
            f"customer_id={customer.id} "
            f"last_order_date={customer.last_order_date.isoformat()}",
            flush=True,
        )


if __name__ == "__main__":
    main()
