"""PanelFlow Studio - Video Saliency and Face-Tracking 9:16 Reframing.

Detects visual focus (faces and visual saliency) in horizontal (16:9) video
and computes smooth, jitter-free 9:16 crop trajectories for YouTube Shorts and Reels.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

logger = logging.getLogger("panelflow.reels.reframer")


@dataclass
class FocalPoint:
    x: float  # Pixel coordinate in original frame
    y: float
    source: Literal["face", "saliency", "center"]
    confidence: float = 1.0


@dataclass
class ReframingKeyframe:
    t: float
    crop_x: int
    crop_y: int
    focal_x: float
    focal_y: float
    source: str


@dataclass
class ReframingTrajectory:
    source_width: int
    source_height: int
    crop_width: int
    crop_height: int
    target_width: int = 1080
    target_height: int = 1920
    mode: str = "shot_stable"
    keyframes: list[ReframingKeyframe] = field(default_factory=list)
    shot_crops: list[dict] = field(default_factory=list)

    def to_ffmpeg_crop_expr(self) -> str:
        """Generate an FFmpeg crop 'x' expression string."""
        if not self.shot_crops and not self.keyframes:
            # Fallback to center crop
            cx = max(0, (self.source_width - self.crop_width) // 2)
            return str(cx)

        if self.mode == "center" or not self.shot_crops:
            cx = max(0, (self.source_width - self.crop_width) // 2)
            return str(cx)

        if len(self.shot_crops) == 1:
            return str(self.shot_crops[0]["crop_x"])

        # Multi-shot piecewise step function: if(lt(t, cut1), x1, if(lt(t, cut2), x2, ... xN))
        expr = str(self.shot_crops[-1]["crop_x"])
        for sc in reversed(self.shot_crops[:-1]):
            cut = sc["end_t"]
            cx = sc["crop_x"]
            expr = f"if(lt(t\\,{cut:.3f})\\,{cx}\\,{expr})"
        return expr

    def to_ffmpeg_vf(self) -> str:
        """Generate full FFmpeg video filter graph (-vf) for cropping and scaling."""
        x_expr = self.to_ffmpeg_crop_expr()
        # Ensure crop width and height are even
        cw = self.crop_width - (self.crop_width % 2)
        ch = self.crop_height - (self.crop_height % 2)
        vf = f"crop={cw}:{ch}:{x_expr}:0,scale={self.target_width}:{self.target_height}:flags=lanczos,setsar=1"
        return vf


class VideoFocalTracker:
    """Detects focal points per frame using face detection with saliency fallback."""

    def __init__(self, enable_face_detect: bool = True):
        self.enable_face_detect = enable_face_detect
        self._face_verifier = None

    def _get_face_verifier(self):
        if self._face_verifier is None and self.enable_face_detect:
            try:
                from engine.characters.face_verify import FaceIdentityVerifier
                self._face_verifier = FaceIdentityVerifier()
            except Exception as exc:
                logger.warning("Could not load FaceIdentityVerifier for reframing: %s", exc)
                self.enable_face_detect = False
        return self._face_verifier

    def detect_frame_focus(self, frame_bgr: np.ndarray) -> FocalPoint:
        """Detect focal center (x, y) in a single BGR video frame."""
        h, w = frame_bgr.shape[:2]
        if h < 20 or w < 20:
            return FocalPoint(x=w / 2.0, y=h / 2.0, source="center", confidence=0.0)

        # 1. Face detection
        if self.enable_face_detect:
            verifier = self._get_face_verifier()
            if verifier is not None:
                try:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    bbox = verifier.detect_face_bbox(frame_rgb)
                    if bbox is not None:
                        x1, y1, x2, y2 = bbox
                        fx = (x1 + x2) / 2.0
                        fy = (y1 + y2) / 2.0
                        # Check that face is not an extreme corner artifact
                        if 0 <= fx <= w and 0 <= fy <= h:
                            return FocalPoint(x=float(fx), y=float(fy), source="face", confidence=0.9)
                except Exception as exc:
                    logger.debug("Face detection exception: %s", exc)

        # 2. Saliency center of mass via gradient energy
        try:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            # Downscale for fast gradient computation
            small_w = min(w, 320)
            scale = small_w / w
            small_h = int(round(h * scale))
            small_gray = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_AREA)

            # Sobel gradients
            gx = cv2.Sobel(small_gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(small_gray, cv2.CV_32F, 0, 1, ksize=3)
            mag = cv2.magnitude(gx, gy)

            # Suppress low noise
            thresh = float(np.percentile(mag, 70))
            mag[mag < thresh] = 0.0

            # Center of mass moments
            M = cv2.moments(mag)
            if M["m00"] > 1e-3:
                cx = (M["m10"] / M["m00"]) / scale
                cy = (M["m01"] / M["m00"]) / scale
                if 0 <= cx <= w and 0 <= cy <= h:
                    return FocalPoint(x=float(cx), y=float(cy), source="saliency", confidence=0.6)
        except Exception as exc:
            logger.debug("Saliency calculation exception: %s", exc)

        # 3. Fallback center
        return FocalPoint(x=w / 2.0, y=h / 2.0, source="center", confidence=0.3)


def probe_video_meta(video_path: Path | str) -> dict:
    """Probe video dimensions, duration, and frame rate via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    import json
    data = json.loads(res.stdout)
    stream = data.get("streams", [{}])[0]
    w = int(stream.get("width", 1920))
    h = int(stream.get("height", 1080))
    
    # Duration
    dur_str = stream.get("duration") or data.get("format", {}).get("duration", "0.0")
    duration = float(dur_str)

    # Frame rate
    fps_str = stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / max(float(den), 1.0)
    else:
        fps = float(fps_str)

    return {"width": w, "height": h, "duration": duration, "fps": fps}


def compute_reframing_plan(
    video_path: Path | str,
    cuts: list[float] | None = None,
    mode: str = "shot_stable",
    target_w: int = 1080,
    target_h: int = 1920,
    sample_fps: float = 2.0,
    enable_face_detect: bool = True,
) -> ReframingTrajectory:
    """Analyze video focal trajectory and produce a smooth 9:16 reframing plan.
    
    Args:
        video_path: Path to source horizontal video.
        cuts: Optional list of shot cut timestamps in seconds.
        mode: 'shot_stable' (stable cinematic crop per shot), 'smooth_pan', or 'center'.
        target_w: Target output width (1080 for Shorts).
        target_h: Target output height (1920 for Shorts).
        sample_fps: Analysis sampling rate in frames per second.
        enable_face_detect: Whether to run SCRFD face detection.
    """
    path = Path(video_path)
    meta = probe_video_meta(path)
    w, h, duration = meta["width"], meta["height"], meta["duration"]

    # Target 9:16 crop width for input height
    crop_h = h
    crop_w = int(round(h * 9.0 / 16.0))
    if crop_w % 2 != 0:
        crop_w -= 1
    # Ensure crop does not exceed source width
    crop_w = min(crop_w, w)

    max_x = max(0, w - crop_w)
    center_x = max_x // 2

    trajectory = ReframingTrajectory(
        source_width=w,
        source_height=h,
        crop_width=crop_w,
        crop_height=crop_h,
        target_width=target_w,
        target_height=target_h,
        mode=mode,
    )

    if mode == "center" or duration <= 0.05:
        trajectory.shot_crops = [{"start_t": 0.0, "end_t": duration, "crop_x": center_x}]
        return trajectory

    # Sample video frames
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        logger.warning("Could not open video file %s, falling back to center crop", path)
        trajectory.shot_crops = [{"start_t": 0.0, "end_t": duration, "crop_x": center_x}]
        return trajectory

    tracker = VideoFocalTracker(enable_face_detect=enable_face_detect)
    step_sec = 1.0 / max(sample_fps, 0.5)
    sample_times = np.arange(0.0, max(duration, step_sec), step_sec)

    keyframes = []
    video_fps = meta["fps"] or 30.0

    for st in sample_times:
        frame_idx = int(round(st * video_fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        focal = tracker.detect_frame_focus(frame)
        # Calculate raw crop_x centered on focal_x
        raw_crop_x = int(round(focal.x - crop_w / 2.0))
        clamped_x = int(np.clip(raw_crop_x, 0, max_x))

        keyframes.append(
            ReframingKeyframe(
                t=float(st),
                crop_x=clamped_x,
                crop_y=0,
                focal_x=focal.x,
                focal_y=focal.y,
                source=focal.source,
            )
        )

    cap.release()

    if not keyframes:
        trajectory.shot_crops = [{"start_t": 0.0, "end_t": duration, "crop_x": center_x}]
        return trajectory

    trajectory.keyframes = keyframes

    # Determine shot segments
    shot_boundaries = [0.0]
    if cuts:
        for c in cuts:
            if 0.1 < c < duration - 0.1 and c not in shot_boundaries:
                shot_boundaries.append(float(c))
    shot_boundaries.append(float(duration))
    shot_boundaries = sorted(list(set(shot_boundaries)))

    # Compute stable crop per shot
    shot_crops = []
    for i in range(len(shot_boundaries) - 1):
        s_start = shot_boundaries[i]
        s_end = shot_boundaries[i + 1]

        shot_kfs = [k for k in keyframes if s_start <= k.t < s_end]
        if shot_kfs:
            # Weighted median: prioritize face detections over saliency
            face_kfs = [k for k in shot_kfs if k.source == "face"]
            target_kfs = face_kfs if face_kfs else shot_kfs
            median_x = int(np.median([k.crop_x for k in target_kfs]))
        else:
            median_x = center_x

        # Ensure even coordinate for strict codec alignment
        if median_x % 2 != 0:
            median_x = max(0, median_x - 1)

        shot_crops.append({
            "shot_index": i + 1,
            "start_t": s_start,
            "end_t": s_end,
            "crop_x": int(median_x),
        })

    trajectory.shot_crops = shot_crops
    return trajectory
