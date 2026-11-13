"""Queue music and speech for the AI Game Studio: POST returns a job id; the finished job's output names a project audio asset."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import ProjectRecord
from engine.database.session import get_db
from engine.jobs.workflow import enqueue_project_operation
from engine.studio_audio import (MUSIC_JOB_TYPE, MUSIC_VRAM_MB, SPEECH_JOB_TYPE, SPEECH_VRAM_MB, generate_music_operation,
                                 generate_speech_operation)

router = APIRouter(prefix="/projects/{project_id}/studio/audio", tags=["studio-audio"])


class StudioMusicRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=1500)
    seconds: float = Field(default=24.0, ge=5.0, le=180.0)
    bpm: int = Field(default=85, ge=40, le=200)
    key_scale: str = Field(default="D Minor", min_length=2, max_length=20)
    seed: int = Field(default=2026, ge=0, le=2**31 - 1)


class StudioSpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str = Field(..., pattern=r"^[a-z]{2}_[a-z]+$", description="a Kokoro voice already on disk, e.g. bm_george")
    speed: float = Field(default=0.95, ge=0.5, le=1.5)


def _require_project(db: Session, project_id: str) -> None:
    if not db.query(ProjectRecord.id).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post("/music")
def queue_studio_music(project_id: str, request: StudioMusicRequest, db: Session = Depends(get_db)) -> dict:
    _require_project(db, project_id)

    def operation(operation_db, progress, is_cancelled):
        return generate_music_operation(operation_db, progress, is_cancelled, project_id=project_id, **request.model_dump())

    job_id = enqueue_project_operation(project_id=project_id, job_type=MUSIC_JOB_TYPE, operation=operation, priority=20, requires_gpu=True,
                                       gpu_vram_mb=MUSIC_VRAM_MB, max_retries=0, job_input=request.model_dump())
    return {"job_id": job_id, "status": "QUEUED"}


@router.post("/speech")
def queue_studio_speech(project_id: str, request: StudioSpeechRequest, db: Session = Depends(get_db)) -> dict:
    _require_project(db, project_id)

    def operation(operation_db, progress, is_cancelled):
        return generate_speech_operation(operation_db, progress, is_cancelled, project_id=project_id, **request.model_dump())

    job_id = enqueue_project_operation(project_id=project_id, job_type=SPEECH_JOB_TYPE, operation=operation, priority=20, requires_gpu=True,
                                       gpu_vram_mb=SPEECH_VRAM_MB, max_retries=0, job_input=request.model_dump())
    return {"job_id": job_id, "status": "QUEUED"}
