from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_pipeline_service, get_repository
from app.db.repository import SupabaseRepository
from app.models.api import PipelineRunAccepted, PipelineRunRequest, PipelineRunStatus
from app.services.pipeline_service import PipelineService

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.post(
    "/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_pipeline(
    payload: PipelineRunRequest,
    request: Request,
    repository: SupabaseRepository = Depends(get_repository),
    service: PipelineService = Depends(get_pipeline_service),
) -> PipelineRunAccepted:
    active = await repository.get_active_pipeline_run()
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Er draait al een pipeline.",
                "run_id": active["id"],
                "status": active["status"],
            },
        )

    run = await repository.create_pipeline_run(payload.model_dump())
    run_id = UUID(run["id"])
    task = asyncio.create_task(service.run(run_id, payload), name=f"pipeline-{run_id}")
    request.app.state.pipeline_tasks[str(run_id)] = task
    task.add_done_callback(
        lambda _: request.app.state.pipeline_tasks.pop(str(run_id), None)
    )

    return PipelineRunAccepted(
        run_id=run_id,
        status="queued",
        status_url=f"{request.app.state.settings.api_prefix}/pipeline/runs/{run_id}",
        message="De crawler is gestart. Gebruik status_url om de voortgang te volgen.",
    )


@router.get("/runs/{run_id}", response_model=PipelineRunStatus)
async def get_pipeline_run(
    run_id: UUID,
    repository: SupabaseRepository = Depends(get_repository),
) -> PipelineRunStatus:
    run = await repository.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline-run niet gevonden.")
    return PipelineRunStatus(**run)
