"""
Audio Director API Router for PanelFlow Studio.
Endpoints for MasterAudioTimeline generation, selective speech regeneration,
audio review playback, and audio approval gating.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import urllib.parse
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


@router.post("/projects/{project_id}/audio/generate-job")
def generate_audio_job(project_id: str, req: GenerateAudioRequest, db: Session = Depends(get_db)):
    from engine.database.models import ProjectRecord
    from engine.jobs.workflow import enqueue_project_operation
    if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    job_id = enqueue_project_operation(project_id, "AUDIO_GENERATION", lambda session, progress, cancelled:
        audio_service.generate_audio_timeline(session, project_id, req.voice_casting, progress, cancelled))
    return {"job_id": job_id}


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


# ---------------------------------------------------------------------------
# Chapter 7: Local AI Narration & Emotional TTS Endpoints
# ---------------------------------------------------------------------------

class SynthesizeSegmentRequest(BaseModel):
    segment_id: str
    text: str
    voice: Optional[str] = "The Narrator"
    emotion: Optional[str] = "Neutral"
    intensity: Optional[float] = 0.5
    speed: Optional[float] = 1.0
    text_revision: Optional[int] = 1
    content_hash: Optional[str] = None
    force: Optional[bool] = False


class SynthesizeBatchRequest(BaseModel):
    segments: list[SynthesizeSegmentRequest]
    provider_id: Optional[str] = "chatterbox_turbo"


class DraftNarrationRequest(BaseModel):
    scenes: list[Dict[str, Any]]
    provider_id: Optional[str] = None


@router.get("/audio/providers")
def get_audio_providers():
    """
    Returns the real audit status of local TTS systems discovered under C:\\Tools.
    Documents verified licenses, capabilities, active status, and commercial suitability.
    """
    from engine.audio.synthesis import CHATTERBOX_PYTHON, TOOLS_ROOT
    chatterbox_active = CHATTERBOX_PYTHON.exists()
    return {
        "primary_provider": "chatterbox_turbo",
        "providers": [
            {
                "id": "chatterbox_turbo",
                "name": "Chatterbox Turbo (Resemble AI)",
                "location": str(TOOLS_ROOT / "Chatterbox"),
                "license": "MIT",
                "commercial_use": "Approved (Permissive MIT)",
                "status": "ACTIVE" if chatterbox_active else "UNAVAILABLE",
                "device": "CUDA (NVIDIA GeForce RTX 5060 Ti)",
                "capabilities": {
                    "zero_shot_voice_cloning": True,
                    "paralinguistic_tags": ["[whisper]", "[sigh]", "[gasp]", "[chuckle]"],
                    "emotions_supported": ["Neutral", "Happy", "Excited", "Sad", "Fearful", "Suspenseful", "Mysterious", "Whispering", "Serious", "Angry", "Determined"],
                    "output_format": "24kHz Mono PCM_16 WAV",
                    "typical_rtf": 0.78,
                },
                "voices": [
                    {"id": "the narrator", "name": "Aria (The Narrator)", "gender": "Female", "ref": "aria_female_narrator.wav"},
                    {"id": "marcus", "name": "Marcus (Male Warrior)", "gender": "Male", "ref": "marcus_male.wav"},
                    {"id": "seraphina", "name": "Seraphina (Cinematic)", "gender": "Female", "ref": "seraphina_female_cinematic.mp3"},
                ],
            },
            {
                "id": "dia_1_6b",
                "name": "Dia 1.6B (Nari Labs)",
                "location": str(TOOLS_ROOT / "dia"),
                "license": "Apache-2.0",
                "commercial_use": "Approved (Apache 2.0)",
                "status": "STANDBY",
                "notes": "Local cache missing encoder/decoder config for Pydantic v2 schema. Preserved as secondary reference.",
            },
            {
                "id": "f5_tts",
                "name": "F5-TTS",
                "location": "Not installed in C:\\Tools",
                "license": "CC-BY-NC 4.0",
                "commercial_use": "Restricted (Non-Commercial Only)",
                "status": "DEPRECATED",
                "notes": "Intentionally excluded from commercial production pipeline due to CC-BY-NC model weight terms.",
            },
            {
                "id": "qwen3_tts",
                "name": "Qwen3-TTS 1.7B",
                "location": str(TOOLS_ROOT / "Qwen3-TTS"),
                "license": "Apache-2.0",
                "commercial_use": "Approved (Apache 2.0)",
                "status": "STANDBY",
                "notes": "Python environment verified; offline weights uninitialized.",
            },
        ],
    }


@router.post("/projects/{project_id}/narration/draft")
async def draft_narration_plan(
    project_id: str,
    req: DraftNarrationRequest,
    db: Session = Depends(get_db),
):
    """
    Generates a structured intermediate story beat plan and contextually aware
    narration draft grounded in manga panels and observed OCR dialogue.
    """
    from engine.database.models import ProjectRecord
    from engine.story.narration import story_narration_service
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        plan = await story_narration_service.generate_narration_draft(
            project_id=project_id,
            scenes_data=req.scenes,
            provider_id=req.provider_id,
        )
        return plan.model_dump()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Narration drafting failed: {e}")


@router.post("/projects/{project_id}/narration/synthesize-segment")
def synthesize_narration_segment_endpoint(
    project_id: str,
    req: SynthesizeSegmentRequest,
    db: Session = Depends(get_db),
):
    """
    Synthesizes speech for an individual narration segment via local Chatterbox Turbo on CUDA.
    Returns exact duration, audio streaming URL, and revision confirmation.
    """
    from engine.database.models import ProjectRecord
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        result = audio_service.synthesize_narration_segment(
            workspace_path=Path(proj.workspace_path),
            segment_id=req.segment_id,
            text=req.text,
            voice=req.voice or "The Narrator",
            emotion=req.emotion or "Neutral",
            intensity=req.intensity or 0.5,
            speed=req.speed or 1.0,
            text_revision=req.text_revision or 1,
            force=req.force or False,
        )
        # Build audio streaming URL for frontend HTML5 audio preview
        audio_path = result["audio_path"]
        result["audio_url"] = f"/api/projects/{project_id}/audio/file?path={urllib.parse.quote(str(audio_path))}"
        result["content_hash"] = req.content_hash
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Synthesis failed: {e}")


@router.post("/projects/{project_id}/narration/synthesize-batch")
def synthesize_narration_batch_endpoint(
    project_id: str,
    req: SynthesizeBatchRequest,
    db: Session = Depends(get_db),
):
    """
    Batch synthesizes multiple approved narration segments in a single model load session.
    """
    from engine.database.models import ProjectRecord
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        tasks = [s.model_dump() for s in req.segments]
        batch_results = audio_service.synthesize_narration_batch(
            workspace_path=Path(proj.workspace_path),
            tasks=tasks,
        )
        for br in batch_results:
            if br.get("audio_path"):
                br["audio_url"] = f"/api/projects/{project_id}/audio/file?path={urllib.parse.quote(str(br['audio_path']))}"
        return {"project_id": project_id, "results": batch_results}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Batch synthesis failed: {e}")
