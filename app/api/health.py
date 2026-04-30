from fastapi import APIRouter

from app.application.services.health_service import HealthService
from app.infrastructure.data_mapper import DATABASE_URL, DataMapper

router: APIRouter = APIRouter(tags=["health"])
data_mapper: DataMapper = DataMapper(DATABASE_URL)
health_service: HealthService = HealthService(data_mapper)


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok" if health_service.health() else "ko",
        "db": "ok" if await health_service.check_db() else "ko",
    }
