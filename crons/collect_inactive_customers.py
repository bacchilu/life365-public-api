import asyncio

from dotenv import load_dotenv

from crons.inactive_customers.workflow import execute_workflow


async def run() -> None:
    load_dotenv()
    await execute_workflow()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
