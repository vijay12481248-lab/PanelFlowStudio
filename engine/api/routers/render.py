"""
Production Renderer API Router for PanelFlow Studio.
Endpoints for starting render jobs, querying real-time progress, cancellation,
MP4 streaming, contact sheet preview, validation reports, and SSE events.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.render.service import render_service

router = APIRouter(prefix="/api", tags=["render"])


class CreateRenderRequest(BaseModel):
    profile_name: str = "standard_1080p"
    custom_output_path: Optional[str] = None
    subtitle_enabled: bool = False
    bgm_volume_db: float = -10.0
    dialogue_gain_db: float = 0.0
    is_draft: bool = False
    timeline_data: Optional[Dict[str, Any]] = None


@router.get("/render/profiles")
def get_render_profiles():
    """Returns available production and draft render profile presets."""
    return {
        "profiles": [
            {
                "id": "standard_1080p",
                "name": "Full HD 1080p (Landscape 16:9)",
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "aspect_ratio": "16:9",
                "video_codec": "H.264 (yuv420p)",
                "audio_codec": "AAC 48kHz Stereo",
                "description": "Recommended for YouTube, Desktop, and Television viewing."
            },
            {
                "id": "vertical_shorts",
                "name": "Vertical 1080p (Portrait 9:16)",
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "aspect_ratio": "9:16",
                "video_codec": "H.264 (yuv420p)",
                "audio_codec": "AAC 48kHz Stereo",
                "description": "Optimized for TikTok, Instagram Reels, and YouTube Shorts."
            },
            {
                "id": "square_feed",
                "name": "Square 1080p (Feed 1:1)",
                "width": 1080,
                "height": 1080,
                "fps": 30,
                "aspect_ratio": "1:1",
                "video_codec": "H.264 (yuv420p)",
                "audio_codec": "AAC 48kHz Stereo",
                "description": "Optimized for Instagram and square social feeds."
            },
            {
                "id": "draft_720p",
                "name": "Fast Draft 720p (Ultra Fast)",
                "width": 1280,
                "height": 720,
                "fps": 30,
                "aspect_ratio": "16:9",
                "video_codec": "H.264 (yuv420p)",
                "audio_codec": "AAC 48kHz Stereo",
                "description": "Rapid rendering for quick proofing and timing checks."
            }
        ]
    }


@router.post("/projects/{project_id}/render/preflight")
def preflight_check_render(
    project_id: str,
    req: CreateRenderRequest,
    db: Session = Depends(get_db),
):
    """
    Validates timeline assets, narration approval state, and audio readiness before rendering.
    """
    try:
        if req.timeline_data:
            return render_service.preflight_check_timeline(db, project_id, req.timeline_data)
        return {"valid": True, "warnings": [], "blockers": [], "stats": {}}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/render/jobs")
def create_render_job(
    project_id: str,
    req: CreateRenderRequest,
    db: Session = Depends(get_db),
):
    try:
        job = render_service.create_and_start_render_job(
            db=db,
            project_id=project_id,
            profile_name=req.profile_name,
            custom_output_path=req.custom_output_path,
            subtitle_enabled=req.subtitle_enabled,
            bgm_volume_db=req.bgm_volume_db,
            dialogue_gain_db=req.dialogue_gain_db,
            is_draft=req.is_draft,
            timeline_data=req.timeline_data,
        )
        return job
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start render: {e}")


@router.get("/projects/{project_id}/render/jobs")
@router.get("/projects/{project_id}/renders")
def list_project_renders(project_id: str, db: Session = Depends(get_db)):
    return render_service.list_project_renders(db, project_id)


@router.get("/projects/{project_id}/render/jobs/{render_id}")
def get_render_job_status(project_id: str, render_id: str, db: Session = Depends(get_db)):
    job = render_service.get_render_job(db, render_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")
    return job


@router.post("/projects/{project_id}/render/jobs/{render_id}/cancel")
def cancel_render_job(project_id: str, render_id: str, db: Session = Depends(get_db)):
    cancelled = render_service.cancel_render_job(db, render_id)
    return {"cancelled": cancelled, "render_id": render_id}


@router.get("/projects/{project_id}/render/jobs/{render_id}/output")
def stream_render_output_video(project_id: str, render_id: str, db: Session = Depends(get_db)):
    job = render_service.get_render_job(db, render_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    out_p = Path(job.get("output_path", "")).resolve()
    if not out_p.exists() or not out_p.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rendered video file not found on disk")

    return FileResponse(path=str(out_p), media_type="video/mp4", filename=out_p.name)


@router.get("/projects/{project_id}/render/jobs/{render_id}/contact-sheet")
def get_render_contact_sheet(project_id: str, render_id: str, db: Session = Depends(get_db)):
    job = render_service.get_render_job(db, render_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    sheet_p = job.get("contact_sheet_path")
    if not sheet_p or not Path(sheet_p).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact sheet not generated or missing")

    p = Path(sheet_p).resolve()
    return FileResponse(path=str(p), media_type="image/jpeg", filename=p.name)


@router.get("/projects/{project_id}/render/jobs/{render_id}/samples/{sample_index}")
def get_render_audit_sample(
    project_id: str,
    render_id: str,
    sample_index: int,
    db: Session = Depends(get_db),
):
    """Serves the exact JPEG audit sample captured during video validation."""
    job = render_service.get_render_job(db, render_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    report = job.get("validation_report")
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation report not found")

    samples = report.get("frame_samples", [])
    if sample_index < 0 or sample_index >= len(samples):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample index out of range")

    sample = samples[sample_index]
    sample_p = Path(sample.get("sample_image_path", "")).resolve()
    if not sample_p.exists() or not sample_p.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit sample image not found on disk")

    return FileResponse(path=str(sample_p), media_type="image/jpeg", filename=sample_p.name)


@router.get("/projects/{project_id}/render/jobs/{render_id}/validation")
def get_render_validation_report(project_id: str, render_id: str, db: Session = Depends(get_db)):
    job = render_service.get_render_job(db, render_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render job not found")

    report = job.get("validation_report")
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation report not found")
    return report


@router.get("/render/events")
async def stream_render_events(request: Request):
    """
    Server-Sent Events endpoint streaming real-time render progress updates.
    """
    queue = render_service.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment
                    yield ": ping\n\n"
        finally:
            render_service.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
