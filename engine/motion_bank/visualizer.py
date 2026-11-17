"""Visualizer: Renders standard OpenPose/DWPose skeleton frames and control videos."""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np

# OpenPose 18-limb topology pairs
BODY_LIMBS = [
    (1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7),
    (1, 8), (8, 9), (9, 10), (1, 11), (11, 12), (12, 13),
    (1, 0), (0, 14), (14, 16), (0, 15), (15, 17),
]

# Standard OpenPose limb RGB colors
LIMB_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
    (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
    (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255),
    (255, 0, 170),
]

# Keypoints below these confidences are guesses (stylised art, occlusion) and are not drawn.
BODY_MIN_CONF = 0.3
HAND_MIN_CONF = 0.3
FACE_MIN_CONF = 0.3

# Hand finger chains (21 points: 0 is wrist, 1-4 thumb, 5-8 index, 9-12 mid, 13-16 ring, 17-20 pinky)
HAND_FINGERS = [
    [0, 1, 2, 3, 4],
    [0, 5, 6, 7, 8],
    [0, 9, 10, 11, 12],
    [0, 13, 14, 15, 16],
    [0, 17, 18, 19, 20],
]


def draw_skeleton_frame(
    width: int,
    height: int,
    body_kpts: List[Tuple[float, float, float]],
    left_hand: Optional[List[Tuple[float, float, float]]] = None,
    right_hand: Optional[List[Tuple[float, float, float]]] = None,
    face_kpts: Optional[List[Tuple[float, float, float]]] = None,
    background: str = "black",
    base_image: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Renders an OpenPose/DWPose skeleton on black canvas or overlay on base_image.
    Coordinates are assumed normalized to [0, 1].
    Returns RGB uint8 image of shape (height, width, 3).
    """
    if base_image is not None and background != "black":
        canvas = base_image.copy()
    else:
        canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # Scale factor for line thickness based on canvas resolution
    scale = max(1, int(round(min(width, height) / 360.0)))

    # 1. Draw Body Limbs
    if body_kpts:
        pts = {}
        for idx, (nx, ny, conf) in enumerate(body_kpts):
            if conf > BODY_MIN_CONF:
                pts[idx] = (int(nx * width), int(ny * height))

        for limb_idx, (p1, p2) in enumerate(BODY_LIMBS):
            if p1 in pts and p2 in pts:
                color = LIMB_COLORS[limb_idx % len(LIMB_COLORS)]
                cv2.line(canvas, pts[p1], pts[p2], color, thickness=scale * 2, lineType=cv2.LINE_AA)

        for idx, pt in pts.items():
            cv2.circle(canvas, pt, radius=scale * 3, color=(0, 0, 255), thickness=-1, lineType=cv2.LINE_AA)

    # 2. Draw Hands
    for hand_kpts, hand_color in [(left_hand, (0, 255, 255)), (right_hand, (255, 0, 255))]:
        if hand_kpts and len(hand_kpts) >= 21:
            hpts = {}
            for hidx, (hx, hy, hconf) in enumerate(hand_kpts):
                if hconf > HAND_MIN_CONF:
                    hpts[hidx] = (int(hx * width), int(hy * height))

            for finger in HAND_FINGERS:
                for k in range(len(finger) - 1):
                    p1, p2 = finger[k], finger[k + 1]
                    if p1 in hpts and p2 in hpts:
                        cv2.line(canvas, hpts[p1], hpts[p2], hand_color, thickness=max(1, scale), lineType=cv2.LINE_AA)

            for pt in hpts.values():
                cv2.circle(canvas, pt, radius=max(1, scale), color=(255, 255, 255), thickness=-1, lineType=cv2.LINE_AA)

    # 3. Draw Face Landmarks
    if face_kpts:
        for fx, fy, fconf in face_kpts:
            if fconf > FACE_MIN_CONF:
                fpt = (int(fx * width), int(fy * height))
                cv2.circle(canvas, fpt, radius=max(1, int(scale * 0.8)), color=(255, 255, 255), thickness=-1, lineType=cv2.LINE_AA)

    return canvas


def encode_h264(src: Path, dst: Path) -> Path:
    """Re-encode to H.264 / yuv420p / faststart: OpenCV only writes MPEG-4 part 2, which browsers cannot play."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to encode the skeleton video as H.264 but was not found on PATH")
    r = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "fast", "-movflags", "+faststart", str(dst)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg H.264 encode failed: {r.stderr.strip()[:300]}")
    return dst


def render_pose_image(pose, width: int, height: int, max_side: int | None = None) -> np.ndarray:
    """One FramePoseData as an RGB skeleton picture on black (the picture a pose-aware model or a human looks at)."""
    img = draw_skeleton_frame(width, height, pose.body, pose.left_hand, pose.right_hand, pose.face, background="black")
    if max_side and max(width, height) > max_side:
        k = max_side / max(width, height)
        img = cv2.resize(img, (max(2, int(width * k)), max(2, int(height * k))), interpolation=cv2.INTER_AREA)
    return img


def render_skeleton_video(
    frames_poses: list,
    output_path: Path,
    fps: float,
    width: int,
    height: int,
    background: str = "black",
    h264: bool = True,
) -> Path:
    """Renders a full sequence of FramePoseData into an MP4 (H.264 by default, so the desktop UI can play it)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_name(output_path.stem + ".raw.mp4") if h264 else output_path
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(raw_path), fourcc, fps, (width, height))

    try:
        for pose in frames_poses:
            body = getattr(pose, "body", [])
            left_hand = getattr(pose, "left_hand", None)
            right_hand = getattr(pose, "right_hand", None)
            face = getattr(pose, "face", None)
            frame_rgb = draw_skeleton_frame(width, height, body, left_hand, right_hand, face, background=background)
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)
    finally:
        out.release()

    if h264:
        try:
            encode_h264(raw_path, output_path)
        finally:
            raw_path.unlink(missing_ok=True)
    return output_path
