import sqlite3

SCHEMA_VERSION: int = 1

CREATE_SCHEMA = """
CREATE TABLE sync_run (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE sync_items (
    customer_id INTEGER PRIMARY KEY,
    last_order_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'succeeded', 'failed')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    completed_at TEXT,
    http_status INTEGER,
    error TEXT
);
"""

INSERT_RUN = """
INSERT INTO sync_run (id, schema_version, generated_at)
VALUES (1, :schema_version, :generated_at)
"""

INSERT_CUSTOMER = """
INSERT INTO sync_items (customer_id, last_order_date, status)
VALUES (:customer_id, :last_order_date, 'pending')
"""

UPDATE_RESULT = """
UPDATE sync_items
SET status = :status,
    attempt_count = attempt_count + 1,
    last_attempt_at = :completed_at,
    completed_at = :completed_at,
    http_status = :http_status,
    error = :error
WHERE customer_id = :customer_id
  AND status = 'pending'
"""


def validate_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT schema_version FROM sync_run WHERE id = 1"
    ).fetchone()
    if row is None or row[0] != SCHEMA_VERSION:
        raise RuntimeError("Unsupported inactive customer sync database schema")
