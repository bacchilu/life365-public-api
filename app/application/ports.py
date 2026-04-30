from typing import Protocol


class DataGateway(Protocol):
    async def check_db(self) -> bool: ...
