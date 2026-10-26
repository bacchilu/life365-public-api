"""Internal Makefile helper. There is no production export or refresh action."""

import argparse
import os
import subprocess
import sys
from urllib.parse import quote

from .config import ROOT, TEST_DATABASE, LocalDatabaseError, operation_lock
from .docker import LocalPostgres

_TESTS = (
    "tests/test_postgresql_customer_sync_migration.py",
    "tests/test_postgresql_customer_sync_transactions.py",
    "tests/test_postgresql_customer_sync_create.py",
    "tests/test_postgresql_customer_sync_update.py",
    "tests/test_salesforce_integration_backends.py",
    "tests/test_sandbox_postgresql.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the shared, temporary local PostgreSQL service"
    )
    parser.add_argument("action", choices=("up", "stop", "test"))
    action = parser.parse_args().action
    try:
        with operation_lock():
            postgres = LocalPostgres()
            if action == "stop":
                postgres.stop()
            elif action == "up":
                postgres.up()
            else:
                postgres.up()
                python = ROOT / ".venv/bin/python"
                if not python.exists():
                    raise LocalDatabaseError(
                        "Run `make build` before running the PostgreSQL tests"
                    )
                env = dict(os.environ)
                password = quote(
                    postgres.environment["CUSTOMER_SYNC_TEST_PASSWORD"], safe=""
                )
                env["CUSTOMER_SYNC_TEST_DATABASE_URL"] = (
                    f"postgresql://customer_sync_test:{password}"
                    f"@127.0.0.1:55432/{TEST_DATABASE}"
                )
                # Unit/API test fixtures must never inherit the production DSN.
                env["DATABASE_URL"] = "postgresql://localhost/test"
                return subprocess.call(
                    [str(python), "-m", "pytest", "-q", *_TESTS],
                    cwd=ROOT,
                    env=env,
                )
    except LocalDatabaseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Local database operation interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
