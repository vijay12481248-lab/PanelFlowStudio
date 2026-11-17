"""FastAPI Router for PanelFlow Studio Motion Bank subsystem."""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.acquisition.rights.models import RightsDeclaration
from engine.motion_bank.models import MotionIngestRecord, MotionRecord, MotionSegment
from engine.motion_bank.models_manifest import DWPOSE_MODELS_MANIFEST
from engine.motion_bank.ingest import ingest_motion_source, probe_video
from engine.motion_bank.segmenter import detect_cuts
from engine.motion_bank.dwpose_extractor import DWPoseExtractor, longest_tracked_run
from engine.motion_bank.visualizer import render_pose_image, render_skeleton_video
from engine.motion_bank.storage import MotionBankStorage

router = APIRouter(prefix="/api/motion_bank", tags=["motion_bank"])

_extractor = DWPoseExtractor()
_storage_cache: Dict[Path, MotionBankStorage] = {}
MIN_TRACKED_RUN_SEC = 1.0  # the actor must be followed for at least this long in a row, or the harvest is refused


def get_bank_dir() -> Path:
    """Where the bank lives: PANELFLOW_MOTION_BANK_DIR, else <app data dir>/motion_bank (never the process's cwd)."""
    env = os.environ.get("PANELFLOW_MOTION_BANK_DIR")
    if env:
        return Path(env)
    from engine.config.settings import Settings
    return Settings().app_data_dir / "motion_bank"


def get_storage() -> MotionBankStorage:
    bank_dir = get_bank_dir()
    if bank_dir not in _storage_cache:
        _storage_cache[bank_dir] = MotionBankStorage(bank_dir)
    return _storage_cache[bank_dir]


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
    rights: Optional[RightsDeclaration] = Field(
        default=None,
        description="Needed unless the video was ingested through /ingest (its source.json carries the declaration).",
    )
    synthetic: bool = Field(
        default=False,
        description="Store the deterministic FAKE skeleton instead of running DWPose (tests/demos). Tagged 'synthetic' and kept out of guide training.",
    )


class UpdateMotionRequest(BaseModel):
    action_title: Optional[str] = Field(default=None, min_length=1)
    action_summary: Optional[str] = None
    action_tags: Optional[List[str]] = None


class TrainGuideRequest(BaseModel):
    num_epochs: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=16, ge=1, le=64)
    include_synthetic: bool = False
    text_embedder: str = Field(default="clip", pattern="^(clip|hash)$", description="How action descriptions become vectors; the checkpoint remembers it")


class GenerateChoreographyRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    num_frames: int = Field(default=48, ge=8, le=128)  # the model's position table holds 128 frames
    fps: float = 24.0
    width: int = 960
    height: int = 544
    render_video: bool = True


def _resolve_rights(video_path: Path, declared: Optional[RightsDeclaration], required: bool) -> Dict[str, Any]:
    """Where a harvested video came from and under which declaration. The gate is enforced here as well as at ingest."""
    src_json = video_path.parent / "source.json"
    if src_json.is_file():
        try:
            rec = MotionIngestRecord.model_validate_json(src_json.read_text(encoding="utf-8"))
            if Path(rec.local_path).resolve() == video_path.resolve():
                return {"rights": rec.rights.model_dump(mode="json"), "source_title": rec.title,
                        "source_sha256": rec.sha256, "source_url": rec.source_uri}
        except Exception:
            pass  # an unreadable record is not a declaration
    if declared is None:
        if required:
            raise HTTPException(
                status_code=400,
                detail="This video has no rights declaration: ingest it through /ingest or pass `rights` (UNKNOWN is refused).",
            )
        return {}
    try:
        declared.validate_for_acquisition()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"rights": declared.model_dump(mode="json")}


def _motion_file(motion_id: str, attr: str) -> Path:
    rec = get_storage().get_motion(motion_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} not found")
    path = getattr(rec, attr)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} has no {attr.replace('_path', '').replace('_', ' ')} on disk")
    return Path(path)


@router.get("/status")
def get_motion_bank_status() -> Dict[str, Any]:
    """Returns the operational status of the Motion Bank and model readiness."""
    motions = get_storage().list_motions(limit=500)
    synthetic = sum(1 for m in motions if m.metadata.get("synthetic"))
    return {
        "status": "online",
        "storage_dir": str(get_bank_dir().resolve()),
        "dwpose_ready": _extractor.is_ready(),
        "dwpose_providers": _extractor.providers(),
        "motion_count": len(motions),
        "synthetic_count": synthetic,
        "manifest": DWPOSE_MODELS_MANIFEST,
    }


@router.post("/ingest", response_model=MotionIngestRecord)
def ingest_source(req: IngestRequest) -> MotionIngestRecord:
    """Ingests a video file or YouTube URL under the specified rights declaration."""
    try:
        staging_dir = get_bank_dir() / "staging" / str(uuid.uuid4())[:8]
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

    provenance = _resolve_rights(video_path, req.rights, required=not req.synthetic)

    if not req.synthetic and not _extractor.is_ready():
        raise HTTPException(
            status_code=503,
            detail="DWPose models are not on disk (see /api/motion_bank/status manifest); refusing to store a fake skeleton. "
                   "Pass synthetic=true only for tests or demos.",
        )

    info = probe_video(video_path)
    width, height = info["width"], info["height"]
    fps = info["fps"]

    # 1. Extract poses
    try:
        poses = _extractor.extract_video_stream(
            video_path=video_path,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            synthetic=req.synthetic,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    detected = sum(1 for p in poses if p.body)
    if not poses or detected == 0:
        raise HTTPException(status_code=400, detail="No person was found in this segment.")
    # A motion is one actor in one continuous take: keep the longest stretch in which the actor was followed
    # (a cut, a dissolve or the actor leaving the shot ends it) and drop the rest.
    run_start, run_end = longest_tracked_run(poses)
    if (run_end - run_start) / fps < MIN_TRACKED_RUN_SEC:
        raise HTTPException(
            status_code=422,
            detail=f"The actor was followed for at most {(run_end - run_start) / fps:.1f}s in a row "
                   f"({detected} of {len(poses)} frames); pick a take with a clear full-body subject.",
        )
    segment_frames = len(poses)
    poses = poses[run_start:run_end]
    detected = len(poses)

    motion_id = f"mot_{uuid.uuid4().hex[:12]}"
    bank_dir = get_bank_dir()
    motion_dir = bank_dir / "motions" / motion_id
    motion_dir.mkdir(parents=True, exist_ok=True)

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

    # 3. Thumbnail: the middle detected pose
    detected_poses = [p for p in poses if p.body]
    thumb_path = motion_dir / "thumbnail.jpg"
    thumb = render_pose_image(detected_poses[len(detected_poses) // 2], width, height, max_side=360)
    cv2.imwrite(str(thumb_path), cv2.cvtColor(thumb, cv2.COLOR_RGB2BGR))

    # 4. Create persistent record
    body_conf = [k[2] for p in poses if p.body for k in p.body]
    tags = list(req.action_tags)
    if req.synthetic and "synthetic" not in tags:
        tags.append("synthetic")
    record = MotionRecord(
        id=motion_id,
        source_uri=str(video_path.resolve()),
        action_title=req.action_title,
        action_summary=req.action_summary,
        action_tags=tags,
        duration_sec=round(duration_sec, 3),
        fps=fps,
        frame_count=len(poses),
        resolution=(width, height),
        actor_track_id=1,
        keypoints_path=str(kp_path.resolve()),
        control_video_path=str(control_video_path.resolve()),
        thumbnail_path=str(thumb_path.resolve()),
        metadata={
            **provenance,
            "synthetic": req.synthetic,
            "extractor": "synthetic" if req.synthetic else "dwpose-wholebody-onnx",
            "providers": _extractor.providers(),
            "detected_frames": detected,
            "segment_frames": segment_frames,
            "trimmed": segment_frames != detected,
            "source_start_sec": poses[0].timestamp_sec,
            "source_end_sec": round(poses[-1].timestamp_sec + 1.0 / fps, 3),
            "mean_body_confidence": round(sum(body_conf) / len(body_conf), 3) if body_conf else 0.0,
            "start_sec": req.start_sec,
            "end_sec": req.end_sec,
        },
    )

    # 5. Save to storage
    get_storage().save_motion(record, frames_poses=poses)
    return record


@router.get("/motions", response_model=List[MotionRecord])
def list_motions(
    tag: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[MotionRecord]:
    """Lists motions in the library, optionally filtered by tag."""
    return get_storage().list_motions(tag=tag, limit=limit)


@router.get("/motions/{motion_id}", response_model=MotionRecord)
def get_motion(motion_id: str) -> MotionRecord:
    """Retrieves a single motion record by ID."""
    rec = get_storage().get_motion(motion_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} not found")
    return rec


@router.get("/motions/{motion_id}/control_video")
def get_motion_control_video(motion_id: str) -> FileResponse:
    """The OpenPose skeleton video (H.264) the desktop UI plays and pose-controlled generation consumes."""
    return FileResponse(_motion_file(motion_id, "control_video_path"), media_type="video/mp4")


@router.get("/motions/{motion_id}/thumbnail")
def get_motion_thumbnail(motion_id: str) -> FileResponse:
    return FileResponse(_motion_file(motion_id, "thumbnail_path"), media_type="image/jpeg")


@router.patch("/motions/{motion_id}", response_model=MotionRecord)
def update_motion(motion_id: str, req: UpdateMotionRequest) -> MotionRecord:
    """Rename, re-describe or re-tag a motion."""
    tags = None if req.action_tags is None else [t.strip() for t in req.action_tags if t.strip()]
    rec = get_storage().update_motion(motion_id, req.action_title, req.action_summary, tags)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} not found")
    return rec


@router.delete("/motions/{motion_id}")
def delete_motion(motion_id: str) -> Dict[str, Any]:
    """Removes the motion and its files (skeleton tensor, control video, thumbnail)."""
    rec = get_storage().delete_motion(motion_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Motion {motion_id} not found")
    motions_root = (get_bank_dir() / "motions").resolve()
    motion_dir = (motions_root / motion_id).resolve()
    if motion_dir.parent == motions_root and motion_dir.is_dir():  # never remove anything outside the bank
        shutil.rmtree(motion_dir, ignore_errors=True)
    return {"deleted": motion_id}


@router.get("/generated/{filename}")
def get_generated_control_video(filename: str) -> FileResponse:
    """A control video the guide model generated."""
    if not re.fullmatch(r"gen_[0-9a-f]+_control\.mp4", filename):
        raise HTTPException(status_code=404, detail="Not a generated control video")
    path = get_bank_dir() / "generated" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Generated video not found")
    return FileResponse(path, media_type="video/mp4")


@router.get("/search", response_model=List[MotionRecord])
def search_motions(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[MotionRecord]:
    """Searches motions by action title, summary, or tags."""
    return get_storage().search_motions(query=q, limit=limit)


@router.post("/guide/train")
def train_guide_model(req: TrainGuideRequest) -> Dict[str, Any]:
    """Trains the local Motion-DiT Choreographer on the harvested motion library."""
    from engine.motion_bank.guide.trainer import MotionGuideTrainer
    output_dir = get_bank_dir() / "checkpoints"
    trainer = MotionGuideTrainer(storage=get_storage(), output_dir=output_dir)
    from engine.motion_bank.guide.text_embed import TextEmbedderError
    try:
        res = trainer.train(num_epochs=req.num_epochs, batch_size=req.batch_size,
                            include_synthetic=req.include_synthetic, embedder=req.text_embedder)
    except TextEmbedderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.post("/guide/generate")
def generate_choreography(req: GenerateChoreographyRequest) -> Dict[str, Any]:
    """Generates a new continuous skeleton sequence from an action prompt using the Guide Model."""
    from engine.motion_bank.guide.generator import MotionGenerator
    output_dir = get_bank_dir() / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = get_bank_dir() / "checkpoints" / "choreographer_latest.pt"
    if not ckpt_path.is_file():
        raise HTTPException(status_code=409, detail="The guide model is not trained yet; an untrained model only produces noise. Train it on real motions first.")

    from engine.motion_bank.guide.text_embed import TextEmbedderError
    generator = MotionGenerator(checkpoint_path=ckpt_path)
    try:
        poses = generator.generate(prompt=req.prompt, num_frames=req.num_frames, fps=req.fps)
    except TextEmbedderError as e:
        raise HTTPException(status_code=503, detail=str(e))

    video_path_str = None
    if req.render_video:
        gen_id = f"gen_{uuid.uuid4().hex[:10]}"
        video_path = output_dir / f"{gen_id}_control.mp4"
        render_skeleton_video(frames_poses=poses, output_path=video_path, fps=req.fps, width=req.width, height=req.height)  # the poses returned below
        video_path_str = str(video_path.resolve())

    return {
        "prompt": req.prompt,
        "frame_count": len(poses),
        "fps": req.fps,
        "duration_sec": round(len(poses) / req.fps, 3),
        "control_video_path": video_path_str,
        "control_video_url": f"/api/motion_bank/generated/{Path(video_path_str).name}" if video_path_str else None,
        "poses": [p.model_dump() for p in poses[:5]],
    }
