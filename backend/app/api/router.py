from fastapi import APIRouter

from app.api.routes import admin, caos, dashboard, health, pipeline

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(pipeline.router)
api_router.include_router(caos.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin.router)
