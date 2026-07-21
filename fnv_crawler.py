from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_repository
from app.db.repository import SupabaseRepository

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def dashboard_summary(
    repository: SupabaseRepository = Depends(get_repository),
) -> dict[str, int]:
    return await repository.dashboard_summary()
