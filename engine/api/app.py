from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from engine.config.settings import settings
from engine.database.session import init_db
from engine.jobs.manager import job_manager
from engine.api.routers import projects, pages, panels, ocr, jobs, adapters, system, story, audio, motion, render, music

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("panelflow.engine")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database schema and perform crash recovery
    logger.info("Initializing SQLite database tables...")
    init_db()
    interrupted_count = job_manager.recover_interrupted_jobs()
    if interrupted_count > 0:
        logger.warning(f"Crash recovery marked {interrupted_count} interrupted jobs as FAILED.")
    logger.info("PanelFlow Studio Engine started successfully.")
    yield
    # Shutdown
    logger.info("PanelFlow Studio Engine shutting down.")

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    # Enable CORS for desktop webviews and local browsers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^(https?|tauri)://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(system.router)
    app.include_router(projects.router)
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

    return app

app = create_app()
