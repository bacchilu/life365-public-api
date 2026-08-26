import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from crons.inactive_customers.locking import acquire_job_lock
from crons.inactive_customers.workflow import execute_workflow

DEFAULT_OUTPUT_PATH: Path = Path("data/inactive-customers.json")


async def run() -> None:
    load_dotenv()
    output_path = Path(
        os.environ.get("INACTIVE_CUSTOMERS_OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH))
    )

    lock_path = output_path.with_suffix(".lock")
    with acquire_job_lock(lock_path) as acquired:
        if not acquired:
            print(
                "Inactive customer collection is already running; "
                "skipping this execution",
                flush=True,
            )
            return

        await execute_workflow(output_path)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
