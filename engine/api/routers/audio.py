"""
Audio Director API Router for PanelFlow Studio.
Endpoints for MasterAudioTimeline generation, selective speech regeneration,
audio review playback, and audio approval gating.
"""
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.audio.service import audio_service

router = APIRouter(prefix="/api", tags=["audio"])


class GenerateAudioRequest(BaseModel):
    voice_casting: Optional[Dict[str, str]] = None


class RegenerateSegmentRequest(BaseModel):
    segment_id: str


@router.get("/projects/{project_id}/audio/timeline")
def get_audio_timeline(project_id: str, db: Session = Depends(get_db)):
    timeline = audio_service.get_audio_timeline(db, project_id)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audio timeline found for project. Run audio generation first.",
        )
    return timeline


@router.post("/projects/{project_id}/audio/generate")
def generate_audio_timeline(
    project_id: str,
    req: GenerateAudioRequest,
    db: Session = Depends(get_db),
):
    try:
        result = audio_service.generate_audio_timeline(
            db=db,
            project_id=project_id,
            voice_casting=req.voice_casting,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Audio generation failed: {e}")


@router.post("/projects/{project_id}/audio/regenerate-segment")
def regenerate_segment_audio(
    project_id: str,
    req: RegenerateSegmentRequest,
    db: Session = Depends(get_db),
):
    try:
        result = audio_service.regenerate_segment_audio(
            db=db,
            project_id=project_id,
            segment_id=req.segment_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Segment regeneration failed: {e}")


@router.post("/projects/{project_id}/audio/approve")
def approve_audio_timeline(project_id: str, db: Session = Depends(get_db)):
    try:
        success = audio_service.approve_audio(db, project_id)
        return {"approved": success, "message": "Audio timeline approved."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/projects/{project_id}/audio/file")
def stream_audio_file(
    project_id: str,
    file_path: str = Query(..., alias="path"),
    db: Session = Depends(get_db),
):
    """
    Streams an audio file for frontend HTML5 <audio> preview.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    ext = p.suffix.lower()
    media_types = {
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".mp3": "audio/mpeg",
        ".aac": "audio/aac",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(path=str(p), media_type=media_type, filename=p.name)
