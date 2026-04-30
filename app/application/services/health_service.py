from app.application.exceptions import DBException
from app.application.ports import DataGateway


class HealthService:
    def __init__(self, data_mapper: DataGateway) -> None:
        self._data_mapper = data_mapper

    def health(self) -> bool:
        return True

    async def check_db(self) -> bool:
        try:
            return await self._data_mapper.check_db()
        except Exception as e:
            raise DBException("Database health check failed") from e
