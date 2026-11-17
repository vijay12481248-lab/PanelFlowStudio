"""Motion Bank -> ChronoFlow: turn a stored motion into the first and last picture of a "First + last" card.

A motion is a skeleton sequence. H3 cannot read skeletons, and neither can the image model: drawn skeletons were tried as the pose picture
(measured 2026-11-17) and the model either painted the skeleton lines onto the character or drew the skeleton next to it, with a pose that
did not match. What works is the proven pose transfer with a real picture: the start and end frames of the harvested video are put on the
card's canvas and the chosen character takes their poses (`<Picture 1>` the character, `<Picture 2>` the video frame, see docs/H3_IMAGE_EDIT.md).
Skeleton pictures are only drawn as a quick preview for choosing the range. The card then renders first -> last like any other First + last card. This gives the two poses, not the
path between them: the video model decides the in-between motion.

Pure helpers (no GPU) come first; `stylize_pose` is the only function that talks to ComfyUI.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from engine.motion_bank.models import FramePoseData
from engine.motion_bank.visualizer import draw_skeleton_frame

BODY, LEFT_HAND, RIGHT_HAND = slice(0, 18), slice(18, 39), slice(39, 60)
MIN_BODY_CONFIDENCE = 0.3  # a frame whose best body keypoint is below this is not a usable pose


def pose_from_tensor_row(row: np.ndarray, frame_index: int = 0, timestamp_sec: float = 0.0) -> FramePoseData:
    """One [133, 3] row of a stored motion as a FramePoseData."""
    def pts(sl: slice) -> List[Tuple[float, float, float]]:
        return [(float(x), float(y), float(c)) for x, y, c in row[sl]]

    return FramePoseData(
        frame_index=frame_index, timestamp_sec=timestamp_sec,
        body=pts(BODY), left_hand=pts(LEFT_HAND), right_hand=pts(RIGHT_HAND),
    )


def usable_frames(keypoints: np.ndarray) -> List[int]:
    """Indexes of frames that hold a pose (body keypoints with confidence)."""
    conf = keypoints[:, BODY, 2]
    return [int(i) for i in np.where(conf.max(axis=1) >= MIN_BODY_CONFIDENCE)[0]]


def pick_keyframes(keypoints: np.ndarray, start_pct: float = 0.0, end_pct: float = 1.0) -> Tuple[int, int]:
    """The usable frames nearest to `start_pct` and `end_pct` of the motion (fractions of its length)."""
    if not (0.0 <= start_pct < end_pct <= 1.0):
        raise ValueError("start_pct and end_pct must satisfy 0 <= start < end <= 1")
    usable = usable_frames(keypoints)
    if len(usable) < 2:
        raise ValueError("The motion has fewer than two usable pose frames")
    last = len(keypoints) - 1
    first_idx = min(usable, key=lambda i: abs(i - start_pct * last))
    last_idx = min(usable, key=lambda i: abs(i - end_pct * last))
    if first_idx == last_idx:
        raise ValueError("Start and end fall on the same frame; widen the range")
    return first_idx, last_idx


def render_pose_canvas(pose: FramePoseData, src_w: int, src_h: int, out_w: int, out_h: int) -> np.ndarray:
    """
    The pose as an RGB skeleton picture of `out_w` x `out_h` on black. The source frame is fitted inside the canvas without
    stretching (so a square clip keeps its proportions on a 16:9 card) and the skeleton is drawn where it stood in that frame.
    """
    scale = min(out_w / src_w, out_h / src_h)
    fit_w, fit_h = src_w * scale, src_h * scale
    off_x, off_y = (out_w - fit_w) / 2.0, (out_h - fit_h) / 2.0

    def remap(points):
        if not points:
            return points
        return [((off_x + x * fit_w) / out_w, (off_y + y * fit_h) / out_h, c) for x, y, c in points]

    # Face landmarks are left out: a dotted face invites the image model to copy the dots; the body and hands carry the pose.
    return draw_skeleton_frame(out_w, out_h, remap(pose.body), remap(pose.left_hand), remap(pose.right_hand), None, background="black")


def source_frame_canvas(video_path: Path, frame_no: int, out_w: int, out_h: int) -> np.ndarray:
    """
    Frame `frame_no` of the harvested video as the pose reference picture, fitted inside `out_w` x `out_h` without stretching
    (the edge pixels are replicated into the margin). The image model reads the pose from a real picture, not from a drawn skeleton.
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise ValueError(f"The source video is not readable: {video_path}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_no)))
        ok, bgr = cap.read()
    finally:
        cap.release()
    if not ok:
        raise ValueError(f"Frame {frame_no} of the source video could not be read")
    h, w = bgr.shape[:2]
    scale = min(out_w / w, out_h / h)
    fit_w, fit_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    fitted = cv2.resize(bgr, (fit_w, fit_h), interpolation=cv2.INTER_AREA)
    left, top = (out_w - fit_w) // 2, (out_h - fit_h) // 2
    padded = cv2.copyMakeBorder(fitted, top, out_h - fit_h - top, left, out_w - fit_w - left, cv2.BORDER_REPLICATE)
    return cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)


def png_bytes(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return buf.getvalue()


def stylize_pose(
    character_png: bytes,
    pose_png: bytes,
    hint: str = "",
    *,
    seed: int = 20261117,
    timeout_s: float = 1800.0,
    prefix: str = "panelflow/chronoflow_motion",
) -> Tuple[bytes, str]:
    """Put the character of `character_png` into the pose of `pose_png` (H3-Image edit). Returns (png, caption used)."""
    from engine.comfyui import ComfyUIClient, ComfyUIError, ComfyWorkflowRegistry, WorkflowRegistryError
    from engine.comfyui.art import ArtEngine, EDIT_WORKFLOW_ID
    from engine.comfyui.edit_prompt import compose_transfer_prompt, release_local_model
    from engine.comfyui.service import ComfyImageGenerationError, h3_edit_size

    with Image.open(io.BytesIO(pose_png)) as pose_img:
        width, height = h3_edit_size(*pose_img.size)
        pose_img = pose_img.convert("RGB")
        if (width, height) != pose_img.size:
            pose_img = pose_img.resize((width, height), Image.Resampling.LANCZOS)
        scaled = io.BytesIO()
        pose_img.save(scaled, format="PNG")
        pose_scaled = scaled.getvalue()
    with Image.open(io.BytesIO(character_png)) as art:
        flat = io.BytesIO()
        art.convert("RGB").save(flat, format="PNG")
        character_flat = flat.getvalue()

    client = ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    try:
        registry.load(EDIT_WORKFLOW_ID)
        preflight = registry.preflight(EDIT_WORKFLOW_ID)
    except (ComfyUIError, WorkflowRegistryError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc
    if not preflight["ready"]:
        raise ComfyImageGenerationError(
            f"ComfyUI workflow preflight failed: missing nodes={preflight['missing_nodes']}, missing models={preflight['missing_models']}"
        )

    caption = compose_transfer_prompt(character_flat, pose_scaled, hint)
    release_local_model()  # the local model and the H3 checkpoint do not fit in VRAM together
    try:
        art_image = ArtEngine(client, registry).edit(
            caption, [character_flat, pose_scaled], width=width, height=height, seed=seed, prefix=prefix, timeout=timeout_s,
        )
    except (ComfyUIError, WorkflowRegistryError, ValueError) as exc:
        raise ComfyImageGenerationError(str(exc)) from exc
    return art_image.png, caption
