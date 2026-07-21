from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_repository
from app.db.repository import SupabaseRepository

router = APIRouter(prefix="/caos", tags=["CAO data"])


@router.get("")
async def list_caos(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=100),
    repository: SupabaseRepository = Depends(get_repository),
) -> dict[str, object]:
    items = await repository.list_caos(limit=limit, offset=offset, search=search)
    return {"items": items, "count": len(items), "limit": limit, "offset": offset}


@router.get("/{cao_id}")
async def get_cao(
    cao_id: UUID,
    repository: SupabaseRepository = Depends(get_repository),
) -> dict[str, object]:
    cao = await repository.get_cao(str(cao_id))
    if not cao:
        raise HTTPException(status_code=404, detail="CAO niet gevonden.")
    data = await repository.get_cao_salary_data(str(cao_id))
    return {"cao": cao, **data}


@router.get("/{cao_id}/salary-tables")
async def get_salary_tables(
    cao_id: UUID,
    repository: SupabaseRepository = Depends(get_repository),
) -> dict[str, object]:
    cao = await repository.get_cao(str(cao_id))
    if not cao:
        raise HTTPException(status_code=404, detail="CAO niet gevonden.")
    data = await repository.get_cao_salary_data(str(cao_id))
    return {"cao": cao, "salary_tables": data["salary_tables"]}
