"""
Audio Director API Router for PanelFlow Studio.
Endpoints for MasterAudioTimeline generation, selective speech regeneration,
audio review playback, and audio approval gating.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import logging
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, status

from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.database.session import get_db
from engine.audio.service import audio_service
from engine.security.paths import (
    contained_file_response,
    project_path,
    read_contained_bytes,
    resolve_contained_path,
    write_contained_image,
)

router = APIRouter(prefix="/api", tags=["audio"])
logger = logging.getLogger("panelflow.api.audio")


class GenerateAudioRequest(BaseModel):
    voice_casting: Optional[Dict[str, str]] = None


class RegenerateSegmentRequest(BaseModel):
    segment_id: str


@router.post("/projects/{project_id}/audio/generate-job")
def generate_audio_job(project_id: str, req: GenerateAudioRequest, db: Session = Depends(get_db)):
    from engine.database.models import ProjectRecord
    from engine.jobs.workflow import audio_script_snapshot, build_operation, enqueue_project_operation
    if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    script_snapshot = audio_script_snapshot(db, project_id)
    provider_id, model_name = audio_service.resolve_tts_provider_identity(db, project_id)
    voice_casting = audio_service.resolve_voice_casting(req.voice_casting)
    job_input = {
        "script_snapshot": script_snapshot,
        "tts_provider_id": provider_id,
        "tts_model_name": model_name,
        "voice_casting": voice_casting,
    }
    operation = build_operation("AUDIO_GENERATION", project_id, job_input)
    if operation is None:
        raise HTTPException(status_code=500, detail="Audio generation job factory is unavailable")
    job_id = enqueue_project_operation(
        project_id,
        "AUDIO_GENERATION",
        operation,
        job_input=job_input,
    )
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
    from engine.database.models import ProjectRecord

    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    workspace = Path(project.workspace_path)
    try:
        p = resolve_contained_path(workspace, file_path, must_be_file=True)
    except (FileNotFoundError, ValueError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    ext = p.suffix.lower()
    media_types = {
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".mp3": "audio/mpeg",
        ".aac": "audio/aac",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    try:
        return contained_file_response(workspace, p, media_type=media_type, filename=p.name)
    except (FileNotFoundError, ValueError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")


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
    model_name: Optional[str] = None


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
    from engine.database.models import (
        ProjectRecord,
        TextRegionRecord,
        PanelRecord,
        PageRecord,
        CharacterRecord,
        LocationRecord,
    )
    from engine.story.narration import story_narration_service
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Fetch ground-truth pages, text regions, characters, and panels from database
    db_pages = (
        db.query(PageRecord)
        .filter(PageRecord.project_id == project_id, PageRecord.status != "FAILED")
        .order_by(PageRecord.sequence.asc())
        .all()
    )
    db_panels = (
        db.query(PanelRecord)
        .filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED")
        .order_by(PanelRecord.sequence.asc())
        .all()
    )
    db_regions = (
        db.query(TextRegionRecord)
        .filter(TextRegionRecord.project_id == project_id, TextRegionRecord.status != "REJECTED")
        .order_by(TextRegionRecord.sequence_in_panel.asc())
        .all()
    )
    db_characters = (
        db.query(CharacterRecord)
        .filter(CharacterRecord.project_id == project_id)
        .all()
    )

    characters_data = [
        {
            "id": c.id,
            "name": c.display_name,
            "canonical_name": c.canonical_name or c.display_name,
            "role": c.role,
            "description": c.description,
            "visual_traits": c.visual_traits if isinstance(c.visual_traits, list) else [],
            "aliases": c.aliases if isinstance(c.aliases, list) else [],
        }
        for c in db_characters
    ]

    panel_to_page_map = {p.id: p.page_id for p in db_panels}
    page_id_to_seq = {pg.id: pg.sequence for pg in db_pages}
    page_id_to_file = {pg.id: pg.filename for pg in db_pages}

    # Build page-level metadata
    pages_data = []
    for pg in db_pages:
        pg_panels = [p for p in db_panels if p.page_id == pg.id]
        pg_regions = [r for r in db_regions if r.page_id == pg.id]
        pg_ocr = [
            (r.corrected_text or r.raw_text or "").strip()
            for r in pg_regions
            if (r.corrected_text or r.raw_text)
        ]
        pages_data.append({
            "id": pg.id,
            "sequence": pg.sequence,
            "filename": pg.filename,
            "panel_ids": [p.id for p in pg_panels],
            "ocr_lines": pg_ocr,
            "panels_count": len(pg_panels),
        })

    panel_ocr_map: Dict[str, list[str]] = {}
    panel_speaker_map: Dict[str, str] = {}
    panel_crop_map: Dict[str, str] = {}
    for p in db_panels:
        if p.crop_filename:
            panel_crop_map[p.id] = p.crop_filename

    for r in db_regions:
        text = (r.corrected_text or r.raw_text or "").strip()
        if text:
            panel_ocr_map.setdefault(r.panel_id, []).append(text)
            if r.speaker_character_id and r.panel_id not in panel_speaker_map:
                panel_speaker_map[r.panel_id] = r.speaker_character_id

    # Enrich incoming scenes or construct from panels if empty
    scenes_data = [dict(s) for s in (req.scenes or [])]
    if not scenes_data and db_panels:
        for idx, p in enumerate(db_panels, start=1):
            ocr_lines = panel_ocr_map.get(p.id, [])
            matched_page_id = panel_to_page_map.get(p.id)
            scenes_data.append({
                "id": f"scene_{idx}",
                "sequence": idx,
                "title": f"Scene {idx}",
                "visual_description": f"Panel #{p.sequence} visual composition",
                "ocr_text": " ".join(ocr_lines),
                "panel_ids": [p.id],
                "page_id": matched_page_id,
                "page_sequence": page_id_to_seq.get(matched_page_id, 1),
                "crop_filenames": [p.crop_filename] if p.crop_filename else [],
                "characters": [panel_speaker_map.get(p.id, "The Narrator")],
            })
    else:
        for sc in scenes_data:
            pids = sc.get("panel_ids", [])
            crops = [panel_crop_map[pid] for pid in pids if pid in panel_crop_map]
            if crops:
                sc["crop_filenames"] = crops

            if not sc.get("page_id") and pids:
                sc_page_id = next((panel_to_page_map.get(pid) for pid in pids if pid in panel_to_page_map), None)
                if sc_page_id:
                    sc["page_id"] = sc_page_id
                    sc["page_sequence"] = page_id_to_seq.get(sc_page_id, 1)

            if not sc.get("ocr_text"):
                matched_ocr = []
                for pid in pids:
                    if pid in panel_ocr_map:
                        matched_ocr.extend(panel_ocr_map[pid])
                if matched_ocr:
                    sc["ocr_text"] = " ".join(matched_ocr)
            if not sc.get("speaker") or sc.get("speaker") == "Narrator":
                for pid in pids:
                    if pid in panel_speaker_map:
                        sc["speaker"] = panel_speaker_map[pid]
                        break

    try:
        plan = await story_narration_service.generate_narration_draft(
            project_id=project_id,
            scenes_data=scenes_data,
            pages_data=pages_data,
            characters_data=characters_data,
            provider_id=req.provider_id,
            model_name=req.model_name,
            workspace_path=Path(proj.workspace_path) if proj.workspace_path else None,
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


@router.post("/projects/{project_id}/panels/{panel_id}/analyze-vision")
async def analyze_panel_vision_endpoint(
    project_id: str,
    panel_id: str,
    model_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Directly runs local Ollama Vision on a specific manga panel crop to describe characters,
    emotions, actions, and atmosphere in real time.
    """
    from engine.database.models import ProjectRecord, PanelRecord, PageRecord
    from engine.llm.registry import llm_registry
    proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
    if not panel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found")

    workspace = Path(str(proj.workspace_path))
    crop_name = panel.crop_filename or f"panel_{panel.sequence:04d}.jpg"
    try:
        crop_path = project_path(workspace, "panels", str(crop_name))
    except (ValueError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Panel crop path is outside the project workspace")

    if not crop_path.exists():
        page = db.query(PageRecord).filter(PageRecord.id == panel.page_id).first()
        if page:
            try:
                norm_path = resolve_contained_path(workspace, Path("normalized") / f"page_{page.sequence:04d}.jpg", must_be_file=True)
            except (FileNotFoundError, ValueError, OSError):
                try:
                    norm_path = resolve_contained_path(workspace, Path("source") / str(page.filename), must_be_file=True)
                except (FileNotFoundError, ValueError, OSError):
                    norm_path = None
            if norm_path is not None and norm_path.exists():
                from PIL import Image
                import io
                try:
                    with Image.open(io.BytesIO(read_contained_bytes(workspace, norm_path))) as im:
                        crop_box = (
                            max(0, int(panel.x)),
                            max(0, int(panel.y)),
                            min(im.width, int(panel.x + panel.width)),
                            min(im.height, int(panel.y + panel.height)),
                        )
                        if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                            cropped = im.crop(crop_box)
                            write_contained_image(workspace, crop_path, cropped.convert("RGB"), "JPEG", quality=90)
                except Exception as ex:
                    logger.warning(f"On-the-fly crop failed: {ex}")

    if not crop_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel crop file not found")

    prov = llm_registry.get_ollama_provider()
    if not await prov.health_check():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama service is not reachable on 127.0.0.1:11434")

    vision_model = model_name or getattr(prov, "vision_model", "qwen3.5:9b")
    try:
        vis_summary = await prov.analyze_vision(
            image=crop_path,
            prompt="Describe in 1-2 concise, vivid sentences what characters, emotions, actions, and atmosphere are visible in this manga panel.",
            model=vision_model,
        )
        return {
            "panel_id": panel_id,
            "visual_description": vis_summary.strip(),
            "model_used": vision_model,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Vision analysis failed: {e}")
