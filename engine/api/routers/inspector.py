"""REST API router for AI Visual Quality Inspector and Auto-Correction Subsystem."""
from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.inspector.image_inspector import ImageInspector
from engine.inspector.repair import ImageRepairEngine
from engine.inspector.schema import (
    DefectRecord,
    InspectorConfig,
    QualityDecision,
    TemporalDefectRecord,
    VideoQualityDecision,
)
from engine.inspector.temporal import TemporalVideoInspector
from engine.inspector.video_repair import VideoRepairEngine
from engine.jobs.workflow import register_operation_factory

logger = logging.getLogger("panelflow.inspector")
router = APIRouter(prefix="/api/inspector", tags=["inspector"])

# Singletons initialized lazily
_image_inspector: Optional[ImageInspector] = None
_temporal_inspector: Optional[TemporalVideoInspector] = None
_image_repair: Optional[ImageRepairEngine] = None
_video_repair: Optional[VideoRepairEngine] = None


def get_image_inspector() -> ImageInspector:
    global _image_inspector
    if _image_inspector is None:
        _image_inspector = ImageInspector()
    return _image_inspector


def get_temporal_inspector() -> TemporalVideoInspector:
    global _temporal_inspector
    if _temporal_inspector is None:
        _temporal_inspector = TemporalVideoInspector()
    return _temporal_inspector


def get_image_repair() -> ImageRepairEngine:
    global _image_repair
    if _image_repair is None:
        try:
            from engine.comfyui.art import ArtEngine
            art = ArtEngine()
        except Exception:
            art = None
        _image_repair = ImageRepairEngine(art_engine=art)
    return _image_repair


def get_video_repair() -> VideoRepairEngine:
    global _video_repair
    if _video_repair is None:
        _video_repair = VideoRepairEngine(
            image_repair=get_image_repair(),
            temporal_inspector=get_temporal_inspector(),
        )
    return _video_repair


# Request schemas
class ImageInspectRequest(BaseModel):
    image_path: str = Field(..., description="Absolute or relative path to image file")
    character_count: Optional[int] = Field(None, description="Expected number of people/characters")
    character_description: Optional[str] = Field(None, description="Optional description of character appearances")
    prompt: Optional[str] = Field(None, description="Generation prompt for context")
    enable_vlm: bool = Field(True, description="Whether to include Ollama blind VLM multi-tile review")


class VideoInspectRequest(BaseModel):
    video_path: str = Field(..., description="Absolute or relative path to video file")
    sample_fps: float = Field(2.0, ge=0.5, le=30.0, description="Sampling rate in frames per second")
    max_frames: int = Field(120, ge=10, le=1000, description="Max frame sample limit")


class ImageRepairRequest(BaseModel):
    image_path: str = Field(..., description="Path to defective image")
    decision: Optional[QualityDecision] = Field(None, description="Existing QualityDecision if already computed")
    prompt: Optional[str] = Field(None, description="Prompt for inpainting pass")


class VideoRepairRequest(BaseModel):
    video_path: str = Field(..., description="Path to defective video")
    decision: Optional[VideoQualityDecision] = Field(None, description="Existing VideoQualityDecision if already computed")


@router.get("/health")
def inspector_health() -> Dict[str, Any]:
    """Verifies operational readiness of CV models, ONNX runtimes, and local LLM/VLM."""
    comfy_base = Path(r"E:\VIJAY SEKAR\ComfyUI")

    models_status = {
        "yunet": (comfy_base / "models" / "opencv" / "face_detection_yunet_2023mar.onnx").is_file(),
        "sface": (comfy_base / "models" / "opencv" / "face_recognition_sface_2021dec.onnx").is_file(),
        "dwpose": (comfy_base / "models" / "dwpose" / "dw-ll_ucoco_384.onnx").is_file(),
        "yolox": (comfy_base / "models" / "dwpose" / "yolox_l.onnx").is_file(),
        "animagine_sdxl_inpaint": (comfy_base / "models" / "checkpoints" / "animagine-xl-4.0.safetensors").is_file(),
    }

    # Probe Ollama readiness
    ollama_ready = False
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"User-Agent": "PanelFlow"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            ollama_ready = resp.status == 200
    except Exception:
        ollama_ready = False

    all_ready = all(models_status.values()) and ollama_ready

    return {
        "status": "ready" if all_ready else "degraded",
        "models": models_status,
        "ollama_ready": ollama_ready,
        "licensing": {
            "cv_models": "Apache 2.0 (YuNet, SFace, DWPose)",
            "inpaint_checkpoint": "CreativeML Open RAIL++-M (Animagine XL 4.0)",
            "commercial_cleared": True,
        },
        "vram_usage": "0 MB (CV runs on CPU via ONNX Runtime & OpenCV)",
    }


@router.post("/image", response_model=QualityDecision)
def inspect_image_endpoint(req: ImageInspectRequest) -> QualityDecision:
    """Evaluates an image for anatomical defects, extra limbs, distorted faces, and duplicate characters."""
    img_p = Path(req.image_path).resolve()
    if not img_p.is_file():
        raise HTTPException(status_code=404, detail=f"Image file not found: {req.image_path}")

    inspector = get_image_inspector()
    try:
        decision = inspector.inspect_image(
            img_p,
            expected_people=req.character_count,
            prompt=req.prompt,
        )
        return decision
    except Exception as exc:
        logger.exception("Error inspecting image: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/video", response_model=VideoQualityDecision)
def inspect_video_endpoint(req: VideoInspectRequest) -> VideoQualityDecision:
    """Evaluates a video sequence for temporal jitter, flickering limbs, and character identity drift."""
    vid_p = Path(req.video_path).resolve()
    if not vid_p.is_file():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    inspector = get_temporal_inspector()
    try:
        import cv2
        cap = cv2.VideoCapture(str(vid_p))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        cap.release()
        step = max(1, int(round(fps / req.sample_fps))) if req.sample_fps > 0 else 2
        decision = inspector.inspect_video(vid_p, sample_step=step)
        return decision
    except Exception as exc:
        logger.exception("Error inspecting video: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/repair/image")
def repair_image_endpoint(req: ImageRepairRequest) -> Dict[str, Any]:
    """Repairs detected visual/anatomical defects via masked SDXL inpainting or redraw fallback."""
    img_p = Path(req.image_path).resolve()
    if not img_p.is_file():
        raise HTTPException(status_code=404, detail=f"Image file not found: {req.image_path}")

    repair_engine = get_image_repair()
    decision = req.decision
    if decision is None:
        inspector = get_image_inspector()
        decision = inspector.inspect_image(img_p, prompt=req.prompt or "")

    try:
        result = repair_engine.repair_image(
            img_p,
            decision=decision,
            prompt=req.prompt or "",
        )
        return {
            "repaired_image_path": str(result.repaired_image_path) if result.repaired_image_path else None,
            "original_image_path": str(result.original_image_path) if result.original_image_path else None,
            "revalidated_decision": result.revalidated_decision.model_dump(),
            "attempts": result.attempts,
            "actions_taken": result.actions_taken,
            "success": result.success,
            "score_improvement": result.score_improvement,
        }
    except Exception as exc:
        logger.exception("Error repairing image: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/repair/video")
def repair_video_endpoint(req: VideoRepairRequest) -> Dict[str, Any]:
    """Repairs temporal inconsistencies or flickering defects in video files."""
    vid_p = Path(req.video_path).resolve()
    if not vid_p.is_file():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.video_path}")

    video_repair = get_video_repair()
    decision = req.decision
    if decision is None:
        inspector = get_temporal_inspector()
        decision = inspector.inspect_video(vid_p)

    try:
        repaired_p, reval_dec, meta = video_repair.repair_video(vid_p, decision)
        return {
            "repaired_video_path": str(repaired_p),
            "revalidated_decision": reval_dec.model_dump(),
            "metadata": meta,
        }
    except Exception as exc:
        logger.exception("Error repairing video: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# Job Manager Operation Factories
def _visual_inspection_operation(project_id: str, job_input: dict):
    def operation(input_data, progress, is_cancelled):
        target = job_input.get("target_path")
        is_video = job_input.get("is_video", False)
        progress(0.1, f"Starting inspection of {Path(target).name}...")

        if is_video:
            inspector = get_temporal_inspector()
            decision = inspector.inspect_video(target)
        else:
            inspector = get_image_inspector()
            decision = inspector.inspect_image(target, prompt=job_input.get("prompt", ""))

        progress(1.0, f"Inspection complete: {decision.status} (score={decision.overall_score:.1f})")
        return {"decision": decision.model_dump()}

    return operation


def _visual_repair_operation(project_id: str, job_input: dict):
    def operation(input_data, progress, is_cancelled):
        target = job_input.get("target_path")
        is_video = job_input.get("is_video", False)
        progress(0.1, f"Starting auto-repair of {Path(target).name}...")

        if is_video:
            repair_engine = get_video_repair()
            inspector = get_temporal_inspector()
            decision = inspector.inspect_video(target)
            repaired_p, reval_dec, meta = repair_engine.repair_video(target, decision)
            progress(1.0, f"Video repair complete: {reval_dec.status} (score={reval_dec.overall_score:.1f})")
            return {
                "repaired_path": str(repaired_p),
                "decision": reval_dec.model_dump(),
                "metadata": meta,
            }
        else:
            repair_engine = get_image_repair()
            inspector = get_image_inspector()
            decision = inspector.inspect_image(target, prompt=job_input.get("prompt", ""))
            res = repair_engine.repair_image(target, decision=decision, prompt=job_input.get("prompt", ""))
            progress(1.0, f"Image repair complete: {res.decision.status} (score={res.decision.overall_score:.1f})")
            return {
                "repaired_path": str(res.repaired_image_path) if res.repaired_image_path else None,
                "decision": res.decision.model_dump(),
                "attempts": res.attempts,
                "success": res.success,
            }

    return operation


register_operation_factory("VISUAL_QUALITY_INSPECTION", _visual_inspection_operation)
register_operation_factory("VISUAL_QUALITY_REPAIR", _visual_repair_operation)
