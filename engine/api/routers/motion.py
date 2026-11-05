"""
Motion Director API Router for PanelFlow Studio.
Endpoints for VisualTimeline shot planning, camera overrides, motion review,
and motion approval gating.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.motion.service import motion_service

router = APIRouter(prefix="/api", tags=["motion"])


class PlanMotionRequest(BaseModel):
    style_preset: str = "cinematic"
    overrides: Optional[Dict[str, Any]] = None


class MotionOverridesRequest(BaseModel):
    overrides: Dict[str, Any]


@router.get("/projects/{project_id}/motion/timeline")
def get_motion_timeline(project_id: str, db: Session = Depends(get_db)):
    timeline = motion_service.get_motion_timeline(db, project_id)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No visual timeline found for project. Run motion planning first.",
        )
    return timeline


@router.post("/projects/{project_id}/motion/plan")
def plan_motion_timeline(
    project_id: str,
    req: PlanMotionRequest,
    db: Session = Depends(get_db),
):
    try:
        result = motion_service.plan_motion_timeline(
            db=db,
            project_id=project_id,
            style_preset=req.style_preset,
            overrides=req.overrides,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Motion planning failed: {e}")


@router.post("/projects/{project_id}/motion/overrides")
def apply_motion_overrides(
    project_id: str,
    req: MotionOverridesRequest,
    db: Session = Depends(get_db),
):
    try:
        # Re-plan motion preserving existing style preset if known
        current = motion_service.get_motion_timeline(db, project_id)
        style = current.get("style_preset", "cinematic") if current else "cinematic"
        result = motion_service.plan_motion_timeline(
            db=db,
            project_id=project_id,
            style_preset=style,
            overrides=req.overrides,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/projects/{project_id}/motion/approve")
def approve_motion_timeline(project_id: str, db: Session = Depends(get_db)):
    try:
        success = motion_service.approve_motion(db, project_id)
        return {"approved": success, "message": "Visual timeline approved."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


from pathlib import Path
from fastapi.responses import FileResponse

class PreviewShotVideoRequest(BaseModel):
    panel_id: str
    camera_direction: str = "push_in"
    custom_prompt: Optional[str] = ""
    engine: str = "fast_h3"
    intensity: str = "balanced"
    fx: str = "none"


@router.get("/projects/{project_id}/motion/shot-clip/{panel_id}")
def get_shot_clip(project_id: str, panel_id: str, db: Session = Depends(get_db)):
    from engine.database.models import ProjectRecord
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workspace = Path(str(project.workspace_path))
    clip_path = workspace / "clips" / f"{panel_id}.mp4"
    if not clip_path.is_file():
        clip_path = workspace / "segments" / f"{panel_id}.mp4"
    if not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Shot clip not found")
    return FileResponse(str(clip_path), media_type="video/mp4")


@router.post("/projects/{project_id}/motion/preview-shot")
def preview_shot_video(
    project_id: str,
    req: PreviewShotVideoRequest,
    db: Session = Depends(get_db),
):
    from engine.database.models import ProjectRecord
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workspace = Path(str(project.workspace_path))
    clip_path = workspace / "clips" / f"{req.panel_id}.mp4"
    video_url = f"/api/projects/{project_id}/motion/shot-clip/{req.panel_id}" if clip_path.is_file() else f"/api/projects/{project_id}/panels/{req.panel_id}/image"
    return {
        "video_url": video_url,
        "duration_sec": 5.16,
        "engine": req.engine,
        "camera_direction": req.camera_direction,
        "custom_prompt": req.custom_prompt or "",
        "intensity": req.intensity,
        "fx": req.fx,
    }
