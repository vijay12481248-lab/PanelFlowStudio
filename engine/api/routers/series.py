"""
FastAPI router for Manga Series Scraping, Chapter Discovery, and Batch Video Production.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field

from engine.acquisition.web.series.models import (
    SeriesMetadata,
    CompilationMode,
    BatchVideoConfig,
    BatchJobStatus,
)
from engine.acquisition.web.series.discovery import SmartSeriesDiscoveryEngine
from engine.pipeline.batch_producer import SmartBatchVideoProducer, active_batch_jobs

router = APIRouter(prefix="/api/series", tags=["series"])
discovery_engine = SmartSeriesDiscoveryEngine()
batch_producer = SmartBatchVideoProducer()


class SeriesInspectRequest(BaseModel):
    source_url: str = Field(..., description="Series index URL or individual chapter URL")


class BatchGenerateRequest(BaseModel):
    source_url: str = Field(..., description="Manga series index URL or chapter URL")
    compilation_mode: str = Field(default="individual", description="'individual' or 'compiled'")
    target_duration_minutes: float = Field(default=25.0, description="Target compilation duration in minutes")
    chapter_start: Optional[float] = Field(default=None, description="Starting chapter number (e.g. 921)")
    chapter_end: Optional[float] = Field(default=None, description="Ending chapter number (e.g. 927)")
    chapter_urls: Optional[List[str]] = Field(default=None, description="Explicit list of chapter URLs")
    max_chapters: Optional[int] = Field(default=None, description="Maximum chapters to process")
    tts_voice: str = Field(default="am_michael", description="Neural voice identifier")
    video_profile: str = Field(default="standard_1080p")
    subtitles: bool = Field(default=True)
    output_dir: Optional[str] = None


@router.post("/inspect", response_model=SeriesMetadata)
async def inspect_series(req: SeriesInspectRequest):
    """
    Inspects a manga URL (series index or single chapter), discovering all episodes/chapters,
    numbering ranges, and inferred pattern templates.
    """
    url = req.source_url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_url must not be empty")

    try:
        metadata = await discovery_engine.discover_series(url)
        return metadata
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Series discovery failed: {e}")


@router.post("/batch-generate", response_model=Dict[str, Any])
async def start_batch_generation(req: BatchGenerateRequest, background_tasks: BackgroundTasks):
    """
    Starts an asynchronous batch video production job across multiple chapters/episodes.
    Supports individual episode generation or smart multi-chapter compilation.
    """
    mode = CompilationMode.COMPILED if req.compilation_mode.lower() == "compiled" else CompilationMode.INDIVIDUAL
    config = BatchVideoConfig(
        source_url=req.source_url.strip(),
        compilation_mode=mode,
        target_duration_minutes=req.target_duration_minutes,
        chapter_start=req.chapter_start,
        chapter_end=req.chapter_end,
        chapter_urls=req.chapter_urls,
        max_chapters=req.max_chapters,
        tts_voice=req.tts_voice,
        video_profile=req.video_profile,
        subtitles=req.subtitles,
        output_dir=req.output_dir,
    )

    # Launch background task
    async def _run_job():
        await batch_producer.run_batch(config)

    background_tasks.add_task(_run_job)

    return {
        "status": "QUEUED",
        "message": "Batch production job scheduled successfully",
        "source_url": req.source_url,
        "compilation_mode": mode.value,
        "target_duration_minutes": req.target_duration_minutes,
    }


@router.get("/batch-status/{job_id}", response_model=BatchJobStatus)
async def get_batch_status(job_id: str):
    """
    Retrieves real-time status of a batch video generation job.
    """
    if job_id not in active_batch_jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch job not found: {job_id}")
    return active_batch_jobs[job_id]


@router.get("/batch-jobs", response_model=List[BatchJobStatus])
async def list_batch_jobs():
    """
    Lists all recent and running batch video generation jobs.
    """
    return list(active_batch_jobs.values())
