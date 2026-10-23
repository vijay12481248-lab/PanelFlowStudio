from typing import Optional, List, Dict, Any, Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from engine.history.service import project_history, HistoryFault
from engine.database.models import CharacterRecord
from engine.history.models import HistoryRecord
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.llm.registry import llm_registry
from engine.story.service import story_service
from engine.story.models import (
    NarrativeDocument,
    VideoScript,
    ScriptValidationReport,
)

router = APIRouter(prefix="/api", tags=["story", "script"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class StoryAnalyzeRequest(BaseModel):
    provider_id: Optional[str] = None


CharacterChangeStatus = Literal["NONE", "PENDING_REVIEW", "APPROVED", "REJECTED"]


class CharacterUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    canonical_name: Optional[str] = None
    role: Optional[str] = None
    aliases: Optional[List[str]] = None
    description: Optional[str] = None
    status: Optional[str] = None
    reference_asset_id: Optional[str] = None
    generation_params: Optional[Dict[str, Any]] = None
    proposed_changes: Optional[Dict[str, Any]] = None
    change_status: Optional[CharacterChangeStatus] = None


class CharacterMergeRequest(BaseModel):
    source_character_id: str
    target_character_id: str


class CharacterSplitRequest(BaseModel):
    new_name: str
    panel_ids: List[str]
    reference_asset_id: Optional[str] = None
    generation_params: Optional[Dict[str, Any]] = None
    proposed_changes: Optional[Dict[str, Any]] = None
    change_status: Optional[CharacterChangeStatus] = None


class SceneMergeRequest(BaseModel):
    scene_id_1: str
    scene_id_2: str


class SpeakerAttributionUpdateRequest(BaseModel):
    text_region_id: str
    speaker_character_id: str
    method: str = "MANUAL"


class ScriptGenerateRequest(BaseModel):
    adaptation_profile: str = "FAITHFUL"  # FAITHFUL, CONDENSED, DRAMATIC_NARRATION, ACCESSIBLE_RECAP


class ScriptSegmentUpdateRequest(BaseModel):
    text: Optional[str] = None
    speaker_character_id: Optional[str] = None
    emotion: Optional[str] = None
    intensity: Optional[float] = None
    estimated_duration: Optional[float] = Field(default=None, gt=0)


class ScriptActionRequest(BaseModel):
    action: str


@router.post("/projects/{project_id}/scripts/generate-job")
def generate_script_job(project_id: str, req: ScriptGenerateRequest, db: Session = Depends(get_db)):
    from engine.database.models import ProjectRecord
    from engine.jobs.workflow import build_operation, enqueue_project_operation
    if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    narrative = story_service.get_narrative(db, project_id)
    if narrative is None:
        raise HTTPException(status_code=400, detail="Cannot generate script: No Narrative IR found for project.")
    narrative_snapshot = NarrativeDocument.model_validate(narrative).model_dump(mode="json")
    provider_id, model_name = story_service.resolve_script_provider_identity(narrative)
    job_input = {
        "adaptation_profile": req.adaptation_profile,
        "narrative_snapshot": narrative_snapshot,
        "provider_id": provider_id,
        "model_name": model_name,
    }
    operation = build_operation("SCRIPT_GENERATION", project_id, job_input)
    if operation is None:
        raise HTTPException(status_code=500, detail="Script generation job factory is unavailable")
    return {"job_id": enqueue_project_operation(
        project_id,
        "SCRIPT_GENERATION",
        operation,
        priority=12,
        requires_gpu=True,
        gpu_vram_mb=3000,
        job_input=job_input,
    )}



# ---------------------------------------------------------------------------
# LLM Provider Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/llm/providers")
async def list_llm_providers():
    providers = llm_registry.list_providers()
    results = []
    for p in providers:
        prov = llm_registry.get_provider(p["provider_id"])
        is_healthy = await prov.health_check()
        results.append({
            **p,
            "provider_name": p["display_name"],
            "is_local": p["provider_id"] != "mock_llm",
            "is_multimodal": prov.model_metadata().supports_vision,
            "is_healthy": is_healthy,
        })
    return results


# ---------------------------------------------------------------------------
# Story Analysis & Narrative IR Endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/story/analyze")
def analyze_story(
    project_id: str,
    req: StoryAnalyzeRequest,
    db: Session = Depends(get_db),
):
    try:
        job_id = story_service.analyze_story_project(
            db=db,
            project_id=project_id,
            preferred_provider_id=req.provider_id,
        )
        return {"job_id": job_id, "message": "Story analysis queued successfully."}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/projects/{project_id}/narrative", response_model=NarrativeDocument)
def get_narrative_document(project_id: str, db: Session = Depends(get_db)):
    doc = story_service.get_narrative(db, project_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Narrative IR exists for project.")
    return doc


@router.post("/projects/{project_id}/story/confirm")
def confirm_story(project_id: str, db: Session = Depends(get_db)):
    try:
        proj = story_service.confirm_story(db, project_id)
        return {
            "project_id": proj.id,
            "current_stage": proj.current_stage,
            "message": "Narrative IR approved successfully.",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Character Registry Endpoints (Part 31)
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/characters")
def list_characters(project_id: str, db: Session = Depends(get_db)):
    chars = story_service.list_characters(db, project_id)
    return [
        {
            "id": c.id,
            "display_name": c.display_name,
            "canonical_name": c.canonical_name,
            "aliases": c.aliases or [],
            "description": c.description,
            "visual_traits": c.visual_traits or [],
            "role": c.role,
            "first_panel_id": c.first_panel_id,
            "reference_panel_ids": c.reference_panel_ids or [],
            "reference_asset_id": c.reference_asset_id,
            "generation_params": c.generation_params or {},
            "proposed_changes": c.proposed_changes or {},
            "change_status": c.change_status or "NONE",
            "status": c.status,
            "manual_override": c.manual_override,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in chars
    ]


@router.put("/projects/{project_id}/characters/{character_id}")
def update_character(
    project_id: str,
    character_id: str,
    req: CharacterUpdateRequest,
    expected_revision: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    updates = req.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    head = db.get(HistoryRecord, project_id)
    exp_rev = expected_revision if expected_revision is not None else (head.revision if head else 0)
    try:
        project_history.execute(
            db,
            project_id,
            operation_id=str(uuid4()),
            expected_revision=exp_rev,
            command_type="character.update",
            version=1,
            label=f"Update character {character_id}",
            input={"character_id": character_id, **updates},
        )
    except HistoryFault as e:
        raise HTTPException(status_code=e.status, detail=str(e))

    c = (
        db.query(CharacterRecord)
        .filter(CharacterRecord.project_id == project_id, CharacterRecord.id == character_id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character {character_id} not found")

    return {
        "id": c.id,
        "display_name": c.display_name,
        "canonical_name": c.canonical_name,
        "aliases": c.aliases,
        "description": c.description,
        "visual_traits": c.visual_traits,
        "role": c.role,
        "status": c.status,
        "reference_asset_id": c.reference_asset_id,
        "generation_params": c.generation_params or {},
        "proposed_changes": c.proposed_changes or {},
        "change_status": c.change_status or "NONE",
        "manual_override": c.manual_override,
    }


@router.post("/projects/{project_id}/characters/merge")
def merge_characters(
    project_id: str,
    req: CharacterMergeRequest,
    db: Session = Depends(get_db),
):
    try:
        target = story_service.merge_characters(
            db=db,
            project_id=project_id,
            source_id=req.source_character_id,
            target_id=req.target_character_id,
        )
        return {
            "id": target.id,
            "display_name": target.display_name,
            "aliases": target.aliases,
            "message": "Characters merged successfully.",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/projects/{project_id}/characters/{character_id}/split")
def split_character(
    project_id: str,
    character_id: str,
    req: CharacterSplitRequest,
    db: Session = Depends(get_db),
):
    try:
        new_char = story_service.split_character(
            db=db,
            project_id=project_id,
            character_id=character_id,
            new_name=req.new_name,
            panel_ids=req.panel_ids,
        )
        return {
            "id": new_char.id,
            "display_name": new_char.display_name,
            "canonical_name": new_char.canonical_name,
            "role": new_char.role,
            "reference_asset_id": new_char.reference_asset_id,
            "generation_params": new_char.generation_params or {},
            "proposed_changes": new_char.proposed_changes or {},
            "change_status": new_char.change_status or "NONE",
            "message": "Character identity split successfully.",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Scenes & Speaker Attributions Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/scenes")
def list_scenes(project_id: str, db: Session = Depends(get_db)):
    scenes = story_service.list_scenes(db, project_id)
    return [
        {
            "id": s.id,
            "sequence": s.sequence,
            "title": s.title,
            "panel_start": s.panel_start,
            "panel_end": s.panel_end,
            "summary": s.summary,
            "confidence": s.confidence,
            "boundary_reason": s.boundary_reason,
            "character_ids": s.character_ids or [],
        }
        for s in scenes
    ]


@router.post("/projects/{project_id}/scenes/merge")
def merge_scenes(
    project_id: str,
    req: SceneMergeRequest,
    db: Session = Depends(get_db),
):
    try:
        merged = story_service.merge_scenes(
            db=db,
            project_id=project_id,
            scene_id_1=req.scene_id_1,
            scene_id_2=req.scene_id_2,
        )
        return {"id": merged.id, "title": merged.title, "message": "Scenes merged successfully."}
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Video Script Adaptation Endpoints (Part 35–42)
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/scripts/generate", response_model=VideoScript)
def generate_script(
    project_id: str,
    req: ScriptGenerateRequest,
    db: Session = Depends(get_db),
):
    try:
        return story_service.generate_script(
            db=db,
            project_id=project_id,
            profile=req.adaptation_profile,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/projects/{project_id}/scripts", response_model=Optional[VideoScript])
def get_script(project_id: str, db: Session = Depends(get_db)):
    script = story_service.get_script(db, project_id)
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No script generated yet for this project.")
    return script


@router.put("/projects/{project_id}/scripts/{script_id}/segments/{segment_id}")
def update_script_segment(
    project_id: str,
    script_id: str,
    segment_id: str,
    req: ScriptSegmentUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        seg = story_service.update_script_segment(
            db=db,
            project_id=project_id,
            script_id=script_id,
            segment_id=segment_id,
            text=req.text,
            speaker_character_id=req.speaker_character_id,
            emotion=req.emotion,
            intensity=req.intensity,
            estimated_duration=req.estimated_duration,
        )
        return {
            "id": seg.id,
            "text": seg.text,
            "estimated_duration": seg.estimated_duration,
            "manual_override": seg.manual_override,
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/projects/{project_id}/scripts/{script_id}/segments/{segment_id}/action", response_model=VideoScript)
def edit_script_action(project_id: str, script_id: str, segment_id: str, req: ScriptActionRequest,
                       db: Session = Depends(get_db)):
    from engine.story.script.review import apply_script_action
    try:
        return apply_script_action(db, project_id, script_id, segment_id, req.action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/projects/{project_id}/scripts/{script_id}/validate", response_model=ScriptValidationReport)
def validate_script(project_id: str, script_id: str, db: Session = Depends(get_db)):
    try:
        return story_service.validate_script(db, project_id, script_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/scripts/{script_id}/approve")
def approve_script(project_id: str, script_id: str, db: Session = Depends(get_db)):
    try:
        s_rec = story_service.approve_script(db, project_id, script_id)
        return {
            "script_id": s_rec.id,
            "status": s_rec.status,
            "message": "Script approved! Project advanced to SCRIPT_APPROVED.",
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Visual Storyboard & Narration-to-Frame Alignment Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/storyboard")
def get_storyboard(project_id: str, db: Session = Depends(get_db)):
    """
    Returns the visual storyboard aligning narration sentences with selected manga panels.
    Generates alignment automatically if not yet computed.
    """
    from engine.story.alignment import alignment_service
    try:
        doc = alignment_service.align_script_to_frames(db, project_id)
        return doc.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/projects/{project_id}/storyboard/segments/{segment_id}")
def update_storyboard_segment(
    project_id: str,
    segment_id: str,
    req: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Updates an individual storyboard segment (narration, timing, camera motion, or panel references)
    and locks it as a manual user override.
    """
    from engine.story.alignment import alignment_service, StoryboardSegmentUpdate
    try:
        update_data = StoryboardSegmentUpdate.model_validate(req)
        updated_seg = alignment_service.update_segment(db, project_id, segment_id, update_data)
        return updated_seg.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/projects/{project_id}/storyboard/realign")
def realign_storyboard(project_id: str, db: Session = Depends(get_db)):
    """
    Forces realignment of narration to manga panels, preserving manual user overrides.
    """
    from engine.story.alignment import alignment_service
    try:
        doc = alignment_service.align_script_to_frames(db, project_id, force_realign=True)
        return doc.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

