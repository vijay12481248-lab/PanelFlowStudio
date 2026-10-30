"""
FastAPI router for Automated Anime Review, Video Ingestion, and Recap Video Production.
"""
from typing import Dict, Any, Optional, List
import uuid
import time
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field

from engine.anime.models import (
    AnimeReviewConfig,
    AnimeReviewResult,
    AnimeEpisodeSource,
)
from engine.anime.scene_detector import AnimeSceneClipper
from engine.anime.pipeline import AnimeReviewPipeline

logger = logging.getLogger("panelflow.anime.router")

router = APIRouter(prefix="/api/anime", tags=["anime"])
clipper = AnimeSceneClipper()
pipeline = AnimeReviewPipeline()

active_anime_jobs: Dict[str, Dict[str, Any]] = {}


class AnimeInspectRequest(BaseModel):
    video_path: str = Field(..., description="Local video file path (.mp4, .mkv, .webm)")
    series_title: str = Field(default="Anime Series", description="Series name")
    episode_number: float = Field(default=1.0, description="Episode number")


class AnimeInspectResponse(BaseModel):
    valid: bool
    source_uri: str
    series_title: str
    episode_number: float
    duration_sec: float
    duration_formatted: str
    width: int
    height: int
    resolution: str
    fps: float
    has_audio: bool
    audio_sample_rate: int
    estimated_cuts: int
    error: Optional[str] = None


@router.post("/inspect", response_model=AnimeInspectResponse)
async def inspect_anime_video(req: AnimeInspectRequest):
    """
    Inspects a local anime or video file, extracting stream metadata, duration,
    resolution, audio specs, and estimated scene transitions.
    """
    path = req.video_path.strip().strip('"').strip("'")
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="video_path must not be empty")

    p = Path(path)
    if not p.exists():
        return AnimeInspectResponse(
            valid=False,
            source_uri=path,
            series_title=req.series_title,
            episode_number=req.episode_number,
            duration_sec=0,
            duration_formatted="0:00",
            width=0,
            height=0,
            resolution="Unknown",
            fps=0,
            has_audio=False,
            audio_sample_rate=0,
            estimated_cuts=0,
            error=f"Video file does not exist on disk: {path}",
        )

    try:
        source: AnimeEpisodeSource = clipper.inspect_source(
            video_path=str(p),
            series_title=req.series_title,
            episode_num=req.episode_number,
        )
        mins = int(source.duration_sec // 60)
        secs = int(source.duration_sec % 60)
        dur_fmt = f"{mins}m {secs:02d}s" if mins > 0 else f"{secs}s"
        est_cuts = max(1, int(source.duration_sec / 3.5))

        return AnimeInspectResponse(
            valid=True,
            source_uri=str(p),
            series_title=source.series_title,
            episode_number=source.episode_number,
            duration_sec=source.duration_sec,
            duration_formatted=dur_fmt,
            width=source.width,
            height=source.height,
            resolution=f"{source.width}x{source.height}",
            fps=round(source.fps, 2),
            has_audio=source.has_audio,
            audio_sample_rate=source.audio_sample_rate,
            estimated_cuts=est_cuts,
        )
    except Exception as e:
        logger.exception("Error inspecting anime video %s: %s", path, e)
        return AnimeInspectResponse(
            valid=False,
            source_uri=path,
            series_title=req.series_title,
            episode_number=req.episode_number,
            duration_sec=0,
            duration_formatted="0:00",
            width=0,
            height=0,
            resolution="Unknown",
            fps=0,
            has_audio=False,
            audio_sample_rate=0,
            estimated_cuts=0,
            error=str(e),
        )


@router.post("/generate-review", response_model=Dict[str, Any])
async def start_anime_review(config: AnimeReviewConfig, background_tasks: BackgroundTasks):
    """
    Launches an automated video review and recap production pipeline in the background.
    """
    job_id = f"anime_{uuid.uuid4().hex[:10]}"
    now = time.time()
    active_anime_jobs[job_id] = {
        "job_id": job_id,
        "series_title": config.series_title,
        "episode_number": config.episode_number,
        "status": "QUEUED",
        "progress": 0.01,
        "current_step": "Job queued for scene detection & review formulation",
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }

    async def _run_review():
        job_data = active_anime_jobs[job_id]
        job_data["status"] = "RUNNING"
        job_data["updated_at"] = time.time()

        def _progress(pct: float, msg: str):
            job_data["progress"] = pct
            job_data["current_step"] = msg
            job_data["updated_at"] = time.time()

        try:
            res: AnimeReviewResult = await pipeline.produce_review_video(
                config=config,
                progress_cb=_progress,
            )
            job_data["status"] = "COMPLETED"
            job_data["progress"] = 1.0
            job_data["current_step"] = "Anime review video produced successfully"
            job_data["result"] = res.model_dump() if hasattr(res, "model_dump") else res.dict()
            job_data["updated_at"] = time.time()
        except Exception as e:
            logger.exception("Anime review job %s failed: %s", job_id, e)
            job_data["status"] = "FAILED"
            job_data["error"] = str(e)
            job_data["current_step"] = f"Failed: {e}"
            job_data["updated_at"] = time.time()

    background_tasks.add_task(_run_review)

    return {
        "job_id": job_id,
        "status": "QUEUED",
        "message": f"Anime review pipeline queued for '{config.series_title}' Ep {config.episode_number:g}",
        "config": config.model_dump() if hasattr(config, "model_dump") else config.dict(),
    }


@router.get("/status/{job_id}")
async def get_anime_job_status(job_id: str):
    """
    Retrieves progress and final video path for an active anime review job.
    """
    if job_id not in active_anime_jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Anime review job not found: {job_id}")
    return active_anime_jobs[job_id]


@router.get("/jobs")
async def list_anime_jobs():
    """
    Lists all active or recent anime review jobs.
    """
    return list(active_anime_jobs.values())
