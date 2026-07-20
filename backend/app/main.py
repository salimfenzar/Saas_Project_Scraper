from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.caos import router as caos_router
from app.api.scraper import router as scraper_router


app = FastAPI(
    title="CAO Monitor API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(caos_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "cao-monitor-api",
    }