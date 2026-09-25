"""Read-only administrative operations endpoints."""

from fastapi import APIRouter

from app.services.operations_service import OperationsService

router = APIRouter(prefix="/operations", tags=["Operations"])
_service = OperationsService()


@router.get("/overview")
def operations_overview() -> dict[str, object]:
    return _service.overview()
