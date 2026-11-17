"""FastAPI Router for PanelFlow Studio Motion Bank subsystem."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.acquisition.rights.models import RightsDeclaration
from engine.motion_bank.models import MotionIngestRecord, MotionRecord, MotionSegment
from engine.motion_bank.models_manifest import DWPOSE_MODELS_MANIFEST
from engine.motion_bank.ingest import ingest_motion_source, probe_video
from engine.motion_bank.segmenter import detect_cuts
from engine.motion_bank.dwpose_extractor import DWPoseExtractor
from engine.motion_bank.visualizer import render_skeleton_video
from engine.motion_bank.storage import MotionBankStorage

router = APIRouter(prefix="/api/motion_bank", tags=["motion_bank"])

DEFAULT_BANK_DIR = Path(os.environ.get("PANELFLOW_MOTION_BANK_DIR", r"app_data/motion_bank"))
_storage = MotionBankStorage(DEFAULT_BANK_DIR)
_extractor = DWPoseExtractor()


class IngestRequest(BaseModel):
    source: str
    rights: RightsDeclaration
    title: Optional[str] = None


class SegmentRequest(BaseModel):
    local_path: str
    min_duration_sec: float = Field(default=1.0, ge=0.5)
    scene_threshold: float = Field(default=0.35, ge=0.1, le=1.0)


class ExtractRequest(BaseModel):
    video_path: str
    action_title: str
    action_tags: List[str] = Field(default_factory=list)
    action_summary: str = ""
    start_sec: float = 0.0
    end_sec: Optional[float] = None
    mock_if_missing: bool = True


class TrainGuideRequest(BaseModel):
    num_epochs: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=16, ge=1, le=64)


class GenerateChoreographyRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    num_frames: int = Field(default=48, ge=8, le=240)
    fps: float = 24.0
    width: int = 960
    height: int = 544
    render_video: bool = True


@router.get("/status")
def get_motion_bank_status() -> Dict[str, Any]:
    """Returns the operational status of the Motion Bank and model readiness."""
    return {
        "status": "online",
        "storage_dir": str(DEFAULT_BANK_DIR.resolve()),
        "dwpose_ready": _extractor.is_ready(),
        "manifest": DWPOSE_MODELS_MANIFEST,
    }


@router.post("/ingest", response_model=MotionIngestRecord)
def ingest_source(req: IngestRequest) -> MotionIngestRecord:
    """Ingests a video file or YouTube URL under the specified rights declaration."""
    try:
        staging_dir = DEFAULT_BANK_DIR / "staging" / str(uuid.uuid4())[:8]
        return ingest_motion_source(
            source=req.source,
            workspace=staging_dir,
            rights=req.rights,
            title=req.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.post("/segment", response_model=List[MotionSegment])
def segment_video(req: SegmentRequest) -> List[MotionSegment]:
    """Detects cuts and shot transitions in an ingested video."""
    video_path = Path(req.local_path)
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.local_path}")
    try:
        return detect_cuts(
            video_path=video_path,
            min_duration_sec=req.min_duration_sec,
            scene_threshold=req.scene_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cut detection failed: {e}")


@router.post("/extract", response_model=MotionRecord)
def extract_motion(req: ExtractRequest) -> MotionRecord:
    """Extracts poses from a video segment and stores the record in the Motion Bank."""
    video_path = Path(req.video_path)
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"Source video not found: {req.video_path}")

    motion_id = f"mot_{uuid.uuid4().hex[:12]}"
    motion_dir = DEFAULT_BANK_DIR / "motions" / motion_id
    motion_dir.mkdir(parents=True, exist_ok=True)

    info = probe_video(video_path)
    width, height = info["width"], info["height"]
    fps = info["fps"]

    # 1. Extract poses
    poses = _extractor.extract_video_stream(
        video_path=video_path,
        start_sec=req.start_sec,
        end_sec=req.end_sec,
        mock_if_missing=req.mock_if_missing,
    )

    if not poses:
        raise HTTPException(status_code=400, detail="No pose frames could be extracted from segment.")

    duration_sec = len(poses) / fps
    kp_path = motion_dir / "motion.safetensors"
    control_video_path = motion_dir / "control_openpose.mp4"

    # 2. Render OpenPose skeleton control video
    render_skeleton_video(
        frames_poses=poses,
        output_path=control_video_path,
        fps=fps,
        width=width,
        height=height,
        background="black",
    )

    # 3. Create persistent record
    record = MotionRecord(
        id=motion_id,
        source_uri=str(video_path.resolve()),
        action_title=req.action_title,
        action_summary=req.action_summary,
        action_tags=req.action_tags,
        duration_sec=round(duration_sec, 3),
        fps=fps,
        frame_count=len(poses),
        resolution=(width, height),
        actor_track_id=1,
        keypoints_path=str(kp_path.resolve()),
        control_video_path=str(control_video_path.resolve()),
    )

    # 4. Save to storage
    _storage.save_motion(record, frames_poses=poses)
    return record


@router.get("/motions", response_model=List[MotionRecord])
def list_motions(
    tag: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[MotionRecord]:
    """Lists motions in the library, optionally filtered by tag."""
    return _storage.list_motions(tag=tag, limit=limit)


@router.get("/motions/{motion_id}", response_model=MotionRecord)
def get_motion(motion_id: str) -> MotionRecord:
    """Retrieves a single motion record by ID."""
    rec = _storage.get_motion(motion_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} not found")
    return rec


@router.get("/search", response_model=List[MotionRecord])
def search_motions(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[MotionRecord]:
    """Searches motions by action title, summary, or tags."""
    return _storage.search_motions(query=q, limit=limit)


@router.post("/guide/train")
def train_guide_model(req: TrainGuideRequest) -> Dict[str, Any]:
    """Trains the local Motion-DiT Choreographer on the harvested motion library."""
    from engine.motion_bank.guide.trainer import MotionGuideTrainer
    output_dir = DEFAULT_BANK_DIR / "checkpoints"
    trainer = MotionGuideTrainer(storage=_storage, output_dir=output_dir)
    res = trainer.train(num_epochs=req.num_epochs, batch_size=req.batch_size)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.post("/guide/generate")
def generate_choreography(req: GenerateChoreographyRequest) -> Dict[str, Any]:
    """Generates a new continuous skeleton sequence from an action prompt using the Guide Model."""
    from engine.motion_bank.guide.generator import MotionGenerator
    output_dir = DEFAULT_BANK_DIR / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = DEFAULT_BANK_DIR / "checkpoints" / "choreographer_latest.pt"

    generator = MotionGenerator(checkpoint_path=ckpt_path if ckpt_path.is_file() else None)
    poses = generator.generate(prompt=req.prompt, num_frames=req.num_frames, fps=req.fps)

    video_path_str = None
    if req.render_video:
        gen_id = f"gen_{uuid.uuid4().hex[:10]}"
        video_path = output_dir / f"{gen_id}_control.mp4"
        generator.generate_control_video(
            prompt=req.prompt,
            output_path=video_path,
            num_frames=req.num_frames,
            fps=req.fps,
            width=req.width,
            height=req.height,
        )
        video_path_str = str(video_path.resolve())

    return {
        "prompt": req.prompt,
        "frame_count": len(poses),
        "fps": req.fps,
        "duration_sec": round(len(poses) / req.fps, 3),
        "control_video_path": video_path_str,
        "poses": [p.model_dump() for p in poses[:5]],
    }
