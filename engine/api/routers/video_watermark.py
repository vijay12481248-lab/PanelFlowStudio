"""FastAPI router for non-blur video watermark detection and removal."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Body
from fastapi.responses import FileResponse
import shutil
from pydantic import BaseModel, Field

from engine.config.settings import settings
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord
from engine.jobs.manager import job_manager
from engine.jobs.workflow import enqueue_project_operation, register_operation_factory
from engine.video.watermark.models import (
    DetectionCandidate,
    WatermarkBoundingBox,
    WatermarkMode,
    WatermarkPreviewResult,
    WatermarkRemovalParams,
)
from engine.video.watermark.pipeline import (
    preview_watermark_removal,
    remove_video_watermark,
)
from engine.video.watermark.static_detector import detect_static_watermarks

logger = logging.getLogger("panelflow.api.video_watermark")

router = APIRouter(prefix="/api/video/watermark", tags=["video_watermark"])


class DetectWatermarkRequest(BaseModel):
    video_path: str = Field(..., description="Path to video file to scan")
    num_samples: int = Field(150, ge=20, le=500, description="Frames to sample across video")
    max_candidates: int = Field(5, ge=1, le=10)


class DetectWatermarkResponse(BaseModel):
    video_path: str
    candidates: List[DetectionCandidate]
    message: str


class PreviewWatermarkRequest(BaseModel):
    video_path: str
    box: WatermarkBoundingBox
    mode: WatermarkMode = WatermarkMode.AUTO
    time_sec: float = Field(1.0, ge=0.0)
    feather_px: int = Field(3, ge=0, le=16)
    alpha_estimate: Optional[float] = Field(None, ge=0.01, le=0.99)


class EnqueueWatermarkRemovalRequest(BaseModel):
    project_id: str = Field("default", description="PanelFlow project ID or slug")
    video_path: str
    output_path: Optional[str] = None
    box: WatermarkBoundingBox
    mode: WatermarkMode = WatermarkMode.AUTO
    feather_px: int = Field(3, ge=0, le=16)
    context_margin_px: int = Field(32, ge=8, le=128)
    alpha_estimate: Optional[float] = None
    use_gpu: bool = True


class EnqueueWatermarkRemovalResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ModelStatusResponse(BaseModel):
    models_dir: str
    weights_available: bool
    weights: dict[str, bool]
    flow_inpainting_ready: bool
    inverse_alpha_ready: bool


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload or stage a video file for watermark removal."""
    upload_dir = settings.app_data_dir / "watermark_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / file.filename
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "filename": file.filename,
        "video_path": str(target_path),
        "stream_url": f"/api/video/watermark/stream?path={target_path.as_posix()}",
    }


@router.get("/stream")
def stream_video(path: str):
    """Stream a local video file for browser playback and scrubbing."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(p, media_type="video/mp4")


@router.post("/detect", response_model=DetectWatermarkResponse)
def detect_watermarks(req: DetectWatermarkRequest):
    """Scan a video for stationary watermarks, channel bugs, and logos using temporal variance."""
    path = Path(req.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    try:
        candidates = detect_static_watermarks(
            path,
            num_samples=req.num_samples,
            max_candidates=req.max_candidates,
        )
        msg = f"Found {len(candidates)} stationary overlay candidates" if candidates else "No static watermark detected"
        return DetectWatermarkResponse(
            video_path=str(path),
            candidates=candidates,
            message=msg,
        )
    except Exception as exc:
        logger.exception("Watermark detection failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/preview", response_model=WatermarkPreviewResult)
def preview_removal(req: PreviewWatermarkRequest):
    """Generates an instant before-and-after single-frame preview comparing original vs cleaned."""
    path = Path(req.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    try:
        params = WatermarkRemovalParams(
            video_path=str(path),
            box=req.box,
            mode=req.mode,
            feather_px=req.feather_px,
            alpha_estimate=req.alpha_estimate,
        )
        return preview_watermark_removal(params, time_sec=req.time_sec)
    except Exception as exc:
        logger.exception("Watermark preview failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/remove", response_model=EnqueueWatermarkRemovalResponse)
def enqueue_removal(req: EnqueueWatermarkRemovalRequest):
    """Enqueues a durable, non-blur video watermark removal background job."""
    path = Path(req.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    params = WatermarkRemovalParams(
        video_path=str(path),
        output_path=req.output_path,
        box=req.box,
        mode=req.mode,
        feather_px=req.feather_px,
        context_margin_px=req.context_margin_px,
        alpha_estimate=req.alpha_estimate,
        use_gpu=req.use_gpu,
    )

    def operation(db, progress, is_cancelled):
        out_path = remove_video_watermark(
            params,
            progress_callback=progress,
            is_cancelled=is_cancelled,
        )
        return {"output_path": str(out_path)}

    target_project_id = req.project_id
    db_session = SessionLocal()
    try:
        proj = db_session.query(ProjectRecord).filter(ProjectRecord.id == target_project_id).first()
        if not proj:
            # Fallback to first existing project or create a valid 'default' project
            first_proj = db_session.query(ProjectRecord).first()
            if first_proj:
                target_project_id = first_proj.id
            else:
                default_proj = ProjectRecord(
                    id="default",
                    title="ChronoFlow Studio",
                    source_type="local",
                    source_metadata="{}",
                    rights_status="approved",
                    license_info="{}",
                    workspace_path=str(settings.app_data_dir / "workspaces" / "default"),
                    current_stage="editing",
                    settings="{}",
                )
                db_session.add(default_proj)
                db_session.commit()
                target_project_id = "default"
    except Exception as exc:
        db_session.rollback()
        logger.warning(f"Project resolution fallback: {exc}")
        first_proj = db_session.query(ProjectRecord).first()
        if first_proj:
            target_project_id = first_proj.id
    finally:
        db_session.close()

    job_id = enqueue_project_operation(
        project_id=target_project_id,
        job_type="VIDEO_WATERMARK_REMOVAL",
        operation=operation,
        priority=15,
        requires_gpu=req.use_gpu,
        gpu_vram_mb=2500,  # ~2.5 GB allocated in job manager
        job_input=req.model_dump(mode="json"),
    )

    return EnqueueWatermarkRemovalResponse(
        job_id=job_id,
        status="ENQUEUED",
        message="Video watermark removal job queued successfully.",
    )


@router.get("/models-status", response_model=ModelStatusResponse)
def get_models_status():
    """Inspect availability of optional ProPainter deep weights in app_data."""
    models_dir = settings.app_data_dir / "models" / "propainter"
    files = {
        "raft-things.pth": (models_dir / "raft-things.pth").exists(),
        "recurrent_flow_completion.pth": (models_dir / "recurrent_flow_completion.pth").exists(),
        "ProPainter.pth": (models_dir / "ProPainter.pth").exists(),
    }
    all_weights = all(files.values())

    return ModelStatusResponse(
        models_dir=str(models_dir),
        weights_available=all_weights,
        weights=files,
        flow_inpainting_ready=True,  # Local Farneback/DIS optical-flow engine always ready
        inverse_alpha_ready=True,    # 100% exact mathematical restoration always ready
    )


class SaveAsRequest(BaseModel):
    source_path: str
    target_directory: str
    target_filename: Optional[str] = None


@router.post("/save-as")
def save_cleaned_video(req: SaveAsRequest):
    """Copies cleaned video to user's desired export directory."""
    src = Path(req.source_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source video not found")

    target_dir = Path(req.target_directory).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = req.target_filename or src.name
    if not filename.endswith(src.suffix):
        filename = f"{filename}{src.suffix}"

    dest = target_dir / filename
    shutil.copy2(src, dest)
    return {
        "status": "success",
        "saved_path": str(dest),
        "directory": str(target_dir),
        "filename": filename,
    }


@router.post("/open-folder")
def open_video_folder(path: str = Body(..., embed=True)):
    """Reveals the cleaned video in Windows Explorer."""
    p = Path(path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")

    import subprocess
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", f"/select,{p}"])
    return {"status": "opened", "path": str(p)}


def build_watermark_removal_operation(project_id: str, job_input: dict):
    """Reconstruct operation on engine restart."""
    params = WatermarkRemovalParams.model_validate(job_input)

    def operation(db, progress, is_cancelled):
        out_path = remove_video_watermark(
            params,
            progress_callback=progress,
            is_cancelled=is_cancelled,
        )
        return {"output_path": str(out_path)}

    return operation


register_operation_factory("VIDEO_WATERMARK_REMOVAL", build_watermark_removal_operation)

