from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.application.ports import CheckGateway
from app.application.services.health_service import HealthService
from app.infrastructure.data_mapper import DATABASE_URL, CheckDataMapper

router: APIRouter = APIRouter(tags=["health"])
check_gateway: CheckGateway = CheckDataMapper(DATABASE_URL)
health_service: HealthService = HealthService(check_gateway)


def get_health_service() -> HealthService:
    return health_service


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", summary="Health check", response_model=HealthResponse)
async def health(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> dict[str, str]:
    """
    Check whether the application is running and can connect to the database.
    """
    return {
        "status": "ok" if service.health() else "ko",
        "db": "ok" if await service.check_db() else "ko",
    }
