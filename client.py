from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.db.client import create_supabase_client
from app.db.repository import SupabaseRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_runtime()

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; CaoMonitor/1.0; "
                "+https://localhost)"
            ),
            "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.7",
        },
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    repository = SupabaseRepository(create_supabase_client(settings))
    await repository.mark_stale_runs_failed()

    app.state.settings = settings
    app.state.http_client = http_client
    app.state.repository = repository
    app.state.pipeline_tasks = {}

    yield

    for task in list(app.state.pipeline_tasks.values()):
        task.cancel()
    await http_client.aclose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "Crawlt FNV CAO-pagina's, downloadt PDF's, haalt salaristabellen uit "
        "machineleesbare PDF's en slaat alles op in Supabase."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "CAO Monitor API draait.",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
