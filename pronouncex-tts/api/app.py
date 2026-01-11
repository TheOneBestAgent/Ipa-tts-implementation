from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import admin, dicts, metrics, models, reader, tts
from core.config import load_settings
from core.jobs import init_job_manager


def create_app() -> FastAPI:
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_job_manager(settings, role="api")
        yield

    app = FastAPI(title="pronouncex-tts", version="0.1.0", lifespan=lifespan)
    app.include_router(tts.router)
    app.include_router(reader.router)
    app.include_router(dicts.router)
    app.include_router(models.router)
    app.include_router(metrics.router)
    app.include_router(admin.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
