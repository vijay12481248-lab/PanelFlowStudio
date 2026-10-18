"""
Story-Aware Music API Router for PanelFlow Studio (Chapter 9).

Endpoints for music direction planning, local ACE-Step 1.5 music synthesis,
candidate take review/audition, audio streaming, and timeline track binding.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.database.models import ProjectRecord
from engine.audio.providers.ace_step import local_music_provider
from engine.audio.music_director import story_aware_music_director
from engine.audio.models.music_plan import (
    MusicCuePlan,
    MusicDirectionPlan,
    MusicGenerationRequest,
    MusicTakeRecord,
    SFXCapabilityReport,
)
from engine.system.resources import SystemResourceManager

logger = logging.getLogger("panelflow.api.music")

router = APIRouter(prefix="/api", tags=["music"])
resource_manager = SystemResourceManager()


class UpdateCuePromptRequest(BaseModel):
    cue_id: str
    prompt: str
    bpm: Optional[int] = None
    intensity: Optional[float] = None


class SelectTakeRequest(BaseModel):
    cue_id: str
    take_id: str


class AddTakeToTimelineRequest(BaseModel):
    cue_id: str
    take_id: str
    volume: float = 0.8
    fade_in_sec: float = 1.0
    fade_out_sec: float = 1.5
    loop: bool = True
    start_time_sec: Optional[float] = None


@router.get("/music/health")
def get_music_service_health():
    """
    Returns real-time health and GPU telemetry for local ACE-Step music engine.
    """
    health = local_music_provider.check_health(timeout=2.0)
    gpu_mem = resource_manager.get_gpu_memory()
    return {
        "service": "ACE-Step 1.5 DiT",
        "health": health,
        "gpu": gpu_mem,
        "recommended_tier": "tier6a (16GB class)",
    }


@router.get("/music/sfx/capability")
def get_sfx_capability_report():
    """
    Reports honest local SFX capabilities.
    Explicitly clarifies whether local AI SFX generation is available or
    if curated library audio is used.
    """
    return SFXCapabilityReport(
        local_ai_sfx_model_available=False,
        detected_models=["Chatterbox Turbo (TTS)", "ACE-Step 1.5 (Music/Ambience)"],
        curated_sfx_library_available=True,
        available_categories=[
            "movement",
            "impact",
            "magic",
            "ambient",
            "environmental",
            "character",
            "transitions",
        ],
        notes=(
            "No dedicated local neural sound-effects generator (such as AudioLDM or AudioGen) "
            "is installed in C:\\Tools. To uphold Chapter 9 audio fidelity and avoid arbitrary sample "
            "clipping from music, PanelFlow uses its high-fidelity curated SFX library with precise timeline placement."
        ),
    ).model_dump()


@router.get("/projects/{project_id}/music/plan")
def get_project_music_plan(
    project_id: str,
    force_replan: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Retrieves or generates the structured story-aware MusicDirectionPlan for the project.
    """
    try:
        plan = story_aware_music_director.get_or_create_plan(
            db=db,
            project_id=project_id,
            force_replan=force_replan,
        )
        return plan.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to load music direction plan")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Music plan failure: {e}")


@router.post("/projects/{project_id}/music/plan")
def save_project_music_plan(
    project_id: str,
    plan_data: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Saves user edits to the MusicDirectionPlan.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        plan = MusicDirectionPlan(**plan_data)
        story_aware_music_director.save_plan(Path(proj.workspace_path), plan)
        return {"saved": True, "plan_id": plan.plan_id, "updated_at": plan.updated_at}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid plan payload: {e}")


@router.post("/projects/{project_id}/music/plan/cue-prompt")
def update_cue_prompt(
    project_id: str,
    req: UpdateCuePromptRequest,
    db: Session = Depends(get_db),
):
    """
    Updates the prompt and musical parameters for a specific cue.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        plan = story_aware_music_director.get_or_create_plan(db, project_id)
        updated_cue = story_aware_music_director.update_cue_prompt(
            workspace_path=Path(proj.workspace_path),
            plan=plan,
            cue_id=req.cue_id,
            new_prompt=req.prompt,
            bpm=req.bpm,
            intensity=req.intensity,
        )
        return updated_cue.model_dump()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/music/generate")
async def generate_music_for_cue(
    project_id: str,
    req: MusicGenerationRequest,
    db: Session = Depends(get_db),
):
    """
    Synthesizes a real candidate music take locally via ACE-Step 1.5.
    Coordinates GPU memory admission to prevent concurrent heavy TTS or OOM.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    workspace = Path(proj.workspace_path)
    music_dir = workspace / "audio" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    job_id = f"job_music_{int(time.time())}"
    # 1. Acquire GPU slot to prevent concurrent heavy TTS or rendering jobs
    acquired = await resource_manager.acquire_gpu_slot(job_id, required_vram_mb=0.0)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GPU is currently busy with another synthesis or inference task. Please retry shortly.",
        )

    try:
        cue_id = req.cue_id or "custom_score"
        plan = story_aware_music_director.get_or_create_plan(db, project_id)
        target_cue = next((c for c in plan.cues if c.cue_id == cue_id), None)
        take_index = len(target_cue.takes) + 1 if target_cue else 1

        loop = asyncio.get_running_loop()
        take_record = await loop.run_in_executor(
            None,
            lambda: local_music_provider.generate_music_take(
                project_id=project_id,
                cue_id=cue_id,
                workspace_music_dir=music_dir,
                prompt=req.prompt,
                audio_duration=req.audio_duration,
                bpm=req.bpm,
                key_scale=req.key_scale,
                time_signature=req.time_signature,
                seed=req.seed,
                use_random_seed=req.use_random_seed,
                inference_steps=req.inference_steps,
                guidance_scale=req.guidance_scale,
                model=req.model,
                take_index=take_index,
            ),
        )

        # Attach take to cue in plan
        story_aware_music_director.attach_take_to_cue(
            workspace_path=workspace,
            plan=plan,
            cue_id=cue_id,
            take=take_record,
            set_as_selected=True,
        )

        return take_record.model_dump()

    except Exception as e:
        logger.exception("Music generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Music generation error: {e}",
        )
    finally:
        await resource_manager.release_gpu_slot(job_id)


@router.get("/projects/{project_id}/music/takes")
def list_project_music_takes(
    project_id: str,
    cue_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns all candidate takes for the project, optionally filtered by cue_id.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    workspace = Path(proj.workspace_path)
    music_dir = workspace / "audio" / "music"
    if not music_dir.exists():
        return []

    takes: List[Dict[str, Any]] = []
    for sidecar_path in music_dir.glob("*.music.json"):
        try:
            take_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if cue_id and take_data.get("cue_id") != cue_id:
                continue
            takes.append(take_data)
        except Exception as e:
            logger.warning(f"Failed to parse music sidecar {sidecar_path}: {e}")

    takes.sort(key=lambda t: t.get("created_at", 0), reverse=True)
    return takes


@router.post("/projects/{project_id}/music/takes/{take_id}/select")
def select_candidate_take(
    project_id: str,
    take_id: str,
    req: SelectTakeRequest,
    db: Session = Depends(get_db),
):
    """
    Designates a specific take as the active, approved take for its cue.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        plan = story_aware_music_director.get_or_create_plan(db, project_id)
        updated_plan = story_aware_music_director.select_take(
            workspace_path=Path(proj.workspace_path),
            plan=plan,
            cue_id=req.cue_id,
            take_id=take_id,
        )
        return updated_plan.model_dump()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/music/takes/{take_id}/add-to-timeline")
def add_take_to_timeline(
    project_id: str,
    take_id: str,
    req: AddTakeToTimelineRequest,
    db: Session = Depends(get_db),
):
    """
    Prepares and returns an AudioToTimelineContract (Schema 6A-v1) payload
    for timeline BGM track integration.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    workspace = Path(proj.workspace_path)
    music_dir = workspace / "audio" / "music"
    plan = story_aware_music_director.get_or_create_plan(db, project_id)

    target_cue = next((c for c in plan.cues if c.cue_id == req.cue_id), None)
    take: Optional[MusicTakeRecord] = None
    if target_cue:
        take = next((t for t in target_cue.takes if t.take_id == take_id), None)

    if not take:
        # Search directly from disk sidecars
        for sidecar_path in music_dir.glob("*.music.json"):
            try:
                td = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if td.get("take_id") == take_id:
                    take = MusicTakeRecord(**td)
                    break
            except Exception:
                pass

    if not take:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Music take '{take_id}' not found")

    # Start time defaults to cue start_time if not provided
    start_time = req.start_time_sec if req.start_time_sec is not None else (target_cue.start_time_sec if target_cue else 0.0)

    contract = {
        "schema_version": "6A-v1",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reference": {
            "asset_id": take.take_id,
            "name": f"AI Score: {target_cue.title if target_cue else 'Custom Take'} (Take {take.take_index})",
            "type": "music",
            "category": "background_music",
            "duration_sec": take.duration_sec,
            "file_url": f"/api/projects/{project_id}/music/assets/{Path(take.audio_file_path).name}",
            "target_track": "BGM",
            "volume": req.volume,
            "loop": req.loop,
            "fade_in_sec": req.fade_in_sec,
            "fade_out_sec": req.fade_out_sec,
            "bpm": take.bpm,
            "key": take.key_scale,
            "start_time_sec": start_time,
        },
    }

    return contract


@router.get("/projects/{project_id}/music/assets/{filename}")
def stream_music_asset(
    project_id: str,
    filename: str,
    db: Session = Depends(get_db),
):
    """
    Streams generated WAV/MP3 files for HTML5 <audio> preview and waveform analysis.
    """
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    p = Path(proj.workspace_path) / "audio" / "music" / filename
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio asset '{filename}' not found")

    media_type = "audio/wav" if p.suffix.lower() == ".wav" else "audio/mpeg"
    return FileResponse(path=str(p), media_type=media_type, filename=p.name)
