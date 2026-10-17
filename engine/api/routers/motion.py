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
