from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_repository
from app.db.repository import SupabaseRepository

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(repository: SupabaseRepository = Depends(get_repository)) -> dict[str, str]:
    try:
        await repository.healthcheck()
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"API draait, maar de databaseverbinding faalt: {exc}",
        ) from exc
