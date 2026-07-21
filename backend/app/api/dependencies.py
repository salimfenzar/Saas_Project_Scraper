from __future__ import annotations

import httpx
from fastapi import Request

from app.config import Settings
from app.db.repository import SupabaseRepository
from app.services.pipeline_service import PipelineService



def get_settings_from_request(request: Request) -> Settings:
    return request.app.state.settings



def get_repository(request: Request) -> SupabaseRepository:
    return request.app.state.repository



def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client



def get_pipeline_service(request: Request) -> PipelineService:
    return PipelineService(
        settings=request.app.state.settings,
        repository=request.app.state.repository,
        http_client=request.app.state.http_client,
    )
