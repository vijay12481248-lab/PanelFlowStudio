"""FastAPI router for PanelFlow Studio 1-Click Pipeline Auto-Pilot."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import ProjectRecord
from engine.database.session import get_db
from engine.pipeline.autopilot import (
    AutoPilotStatusResponse,
    get_autopilot_runner,
    start_autopilot_run,
)

router = APIRouter(prefix="/api/projects", tags=["autopilot"])


class AutoPilotStartRequest(BaseModel):
    target_profile: str = Field(default="standard_1080p")
    skip_existing_stages: bool = Field(default=True)
    voice_preset: Optional[str] = None
    enable_thumbnails: bool = Field(default=True)


@router.post("/{project_id}/autopilot/run", response_model=AutoPilotStatusResponse)
async def start_autopilot(
    project_id: str,
    request: AutoPilotStartRequest,
    db: Session = Depends(get_db),
) -> AutoPilotStatusResponse:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    return await start_autopilot_run(
        project_id=project_id,
        options={
            "target_profile": request.target_profile,
            "skip_existing_stages": request.skip_existing_stages,
            "voice_preset": request.voice_preset,
            "enable_thumbnails": request.enable_thumbnails,
        },
    )


@router.get("/{project_id}/autopilot/status", response_model=AutoPilotStatusResponse)
def get_autopilot_status(
    project_id: str,
    db: Session = Depends(get_db),
) -> AutoPilotStatusResponse:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    runner = get_autopilot_runner(project_id)
    return runner.snapshot()


@router.post("/{project_id}/autopilot/cancel")
def cancel_autopilot(
    project_id: str,
    db: Session = Depends(get_db),
) -> dict:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    runner = get_autopilot_runner(project_id)
    runner.cancel()
    return {"cancelled": True, "project_id": project_id}
