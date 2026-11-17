"""ChronoFlow <-> Motion Bank: pick a harvested motion on a "First + last" card and get its start and end pictures.

The Motion Bank itself lives in `engine/api/routers/motion_bank.py`; these routes only expose what a ChronoFlow card needs, under the
`/api/chronoflow` prefix the studio UI already talks to. See `engine/chronoflow/motion_frames.py` for what is produced and its limits.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

import cv2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.api.routers import motion_bank as bank
from engine.chronoflow import motion_frames
from engine.chronoflow.pipeline import COMFY_INPUT_DIR
from engine.chronoflow.scene_render import _frame

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chronoflow", tags=["chronoflow"])

_gpu_lock = asyncio.Lock()  # one picture job at a time: ComfyUI and the local model share the GPU


class MotionFramesRequest(BaseModel):
    motion_id: str
    character_picture: str = Field(description="A picture in the ComfyUI input folder whose character should perform the motion")
    width: int = Field(default=1344, ge=256, le=4096)
    height: int = Field(default=768, ge=256, le=4096)
    start_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    end_pct: float = Field(default=1.0, ge=0.0, le=1.0)
    hint: str = ""
    stylize: bool = Field(default=True, description="false: only draw the skeleton previews and the two source frames (instant, for choosing the range)")
    seed: int = 20261117


@router.get("/motions")
def list_chronoflow_motions() -> dict[str, Any]:
    """Real (non-synthetic) motions that carry a rights record, ready to pick on a card."""
    out = []
    for m in bank.get_storage().list_motions(limit=500):
        if m.metadata.get("synthetic") or not m.metadata.get("rights"):
            continue
        out.append({
            "id": m.id, "title": m.action_title, "tags": m.action_tags, "duration_sec": m.duration_sec, "frames": m.frame_count,
            "rights": m.metadata["rights"].get("status"),
            "thumbnail": f"/api/motion_bank/motions/{m.id}/thumbnail" if m.thumbnail_path else "",
        })
    return {"motions": out}


def _save(name: str, data: bytes) -> str:
    (COMFY_INPUT_DIR / name).write_bytes(data)
    return name


@router.post("/storyboard/motion_frames")
async def storyboard_motion_frames(req: MotionFramesRequest) -> dict[str, Any]:
    """Start and end pictures for a card from a motion: pose pictures always, the character in those poses when `stylize`."""
    rec = bank.get_storage().get_motion(req.motion_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Motion {req.motion_id} not found")
    if rec.metadata.get("synthetic"):
        raise HTTPException(status_code=400, detail="This motion is a fake test skeleton; harvest a real one")
    if not rec.metadata.get("rights"):
        raise HTTPException(status_code=400, detail="This motion has no rights record, so it cannot be used in a video")
    character = _frame(COMFY_INPUT_DIR, req.character_picture, "character picture")
    try:
        keypoints = bank.get_storage().load_keypoints_tensor(Path(rec.keypoints_path)).numpy()
        first_i, last_i = motion_frames.pick_keyframes(keypoints, req.start_pct, req.end_pct)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    src_w, src_h = rec.resolution
    run = uuid.uuid4().hex[:8]
    poses: dict[str, bytes] = {}
    for label, idx in (("first", first_i), ("last", last_i)):
        pose = motion_frames.pose_from_tensor_row(keypoints[idx], idx, idx / rec.fps)
        poses[label] = motion_frames.png_bytes(motion_frames.render_pose_canvas(pose, src_w, src_h, req.width, req.height))
    source = Path(rec.source_uri)
    have_source = source.is_file()
    start_sec = float(rec.metadata.get("source_start_sec") or 0.0)
    refs: dict[str, bytes] = {}
    if have_source:
        try:
            for label, idx in (("first", first_i), ("last", last_i)):
                frame_no = int(round(start_sec * rec.fps)) + idx
                refs[label] = motion_frames.png_bytes(
                    await asyncio.to_thread(motion_frames.source_frame_canvas, source, frame_no, req.width, req.height))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif req.stylize:
        raise HTTPException(
            status_code=400,
            detail=f"The source video of this motion is gone ({rec.source_uri}). The character takes its pose from a real frame of it; "
                   "re-harvest the footage first.")
    result: dict[str, Any] = {
        "motion_id": rec.id, "first_index": first_i, "last_index": last_i, "rights": rec.metadata["rights"].get("status"),
        "pose_first": _save(f"motion_{rec.id}_pose_first_{run}.png", poses["first"]),
        "pose_last": _save(f"motion_{rec.id}_pose_last_{run}.png", poses["last"]),
    }
    for label in refs:
        result[f"ref_{label}"] = _save(f"motion_{rec.id}_ref_{label}_{run}.png", refs[label])
    if not req.stylize:
        return result

    character_png = character.read_bytes()
    async with _gpu_lock:
        try:
            for label in ("first", "last"):
                png, caption = await asyncio.to_thread(
                    motion_frames.stylize_pose, character_png, refs[label], req.hint,
                    seed=req.seed, prefix=f"panelflow/chronoflow_motion/{rec.id}",
                )
                result[f"{label}_frame"] = _save(f"motion_{rec.id}_{label}_{run}.png", png)
                result[f"{label}_caption"] = caption
        except Exception as e:  # ComfyImageGenerationError and friends: report, never substitute the raw skeleton
            logger.warning("Motion frame generation failed: %s", e)
            raise HTTPException(status_code=502, detail=f"Could not draw the character in the pose: {e}")
    return result
