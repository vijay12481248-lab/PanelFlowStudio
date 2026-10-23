from contextlib import asynccontextmanager
import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.config.settings import settings
from engine.database.session import init_db, SessionLocal
from engine.database.models import ProjectRecord
from engine.history.assets import recover_workspaces
from engine.jobs.manager import job_manager
from engine.security.local_api import (
    ENGINE_TOKEN_ENV,
    LocalApiSecurityMiddleware,
    configured_origins,
    insecure_local_api_enabled,
)
from engine.api.routers import projects, pages, panels, ocr, jobs, adapters, system, story, audio, motion, render, music, comfyui
from engine.api.routers import history, backgrounds, packaging, autopilot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("panelflow.engine")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database schema and recover interrupted/expired jobs.
    logger.info("Initializing SQLite database tables...")
    init_db()
    # File commands leave a prepared manifest before changing project assets.
    # Heal those interrupted writes before any endpoint can expose history.
    with SessionLocal() as db:
        recovered_assets = recover_workspaces([row.workspace_path for row in db.query(ProjectRecord.workspace_path).all()])
    if recovered_assets:
        logger.warning("Recovered interrupted retained-asset operations: %s", recovered_assets)
    recovered_count = job_manager.recover_interrupted_jobs()
    expired_count = job_manager.recover_expired_leases()
    if recovered_count or expired_count:
        logger.info("Recovered %s interrupted and %s expired jobs.", recovered_count, expired_count)

    async def recover_leases_periodically():
        while True:
            await asyncio.sleep(15.0)
            try:
                job_manager.recover_expired_leases()
            except Exception:
                logger.exception("Periodic job lease recovery failed")

    recovery_task = asyncio.create_task(recover_leases_periodically())
    logger.info("PanelFlow Studio Engine started successfully.")
    try:
        yield
    finally:
        recovery_task.cancel()
        try:
            await recovery_task
        except asyncio.CancelledError:
            pass
        logger.info("PanelFlow Studio Engine shutting down.")

def create_app(
    *,
    engine_token: str | None = None,
    allowed_origins: set[str] | None = None,
    allow_insecure: bool | None = None,
) -> FastAPI:
    origins = allowed_origins if allowed_origins is not None else configured_origins()
    token = os.getenv(ENGINE_TOKEN_ENV, "") if engine_token is None else engine_token
    insecure = insecure_local_api_enabled() if allow_insecure is None else allow_insecure
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    # Browser access is restricted to the desktop webview and explicitly opted-in
    # development origins. Token validation is performed by the security middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Accept", "Content-Type", "X-PanelFlow-Control", "X-PanelFlow-Token"],
    )
    app.add_middleware(
        LocalApiSecurityMiddleware,
        engine_token=token,
        allowed_origins=origins,
        api_port=settings.api_port,
        allow_insecure=insecure,
    )

    # Include routers
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(history.router)
    app.include_router(backgrounds.router)
    app.include_router(pages.router)
    app.include_router(panels.router)
    app.include_router(ocr.router)
    app.include_router(story.router)
    app.include_router(jobs.router)
    app.include_router(adapters.router)
    app.include_router(audio.router)
    app.include_router(music.router)
    app.include_router(motion.router)
    app.include_router(render.router)
    app.include_router(comfyui.router)
    app.include_router(comfyui.project_router)
    app.include_router(packaging.router)
    app.include_router(autopilot.router)

    return app

app = create_app()
