from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    max_caos: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Leeg/null betekent: alle gevonden cao's verwerken.",
    )
    max_pages: int = Field(default=500, ge=1, le=2000)
    reprocess_existing: bool = False


class PipelineRunAccepted(BaseModel):
    run_id: UUID
    status: str
    status_url: str
    message: str


class MessageResponse(BaseModel):
    message: str


class PipelineRunStatus(BaseModel):
    id: UUID
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
