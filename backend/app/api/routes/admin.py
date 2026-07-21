from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import get_repository, get_settings_from_request
from app.config import Settings
from app.db.repository import SupabaseRepository
from app.models.api import MessageResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/reset-data", response_model=MessageResponse)
async def reset_data(
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_from_request),
    repository: SupabaseRepository = Depends(get_repository),
) -> MessageResponse:
    if not settings.allow_database_reset:
        raise HTTPException(status_code=403, detail="Database reset is uitgeschakeld.")
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Ongeldige admin-token.")
    await repository.reset_data()
    return MessageResponse(message="Alle CAO-monitorgegevens zijn verwijderd.")
