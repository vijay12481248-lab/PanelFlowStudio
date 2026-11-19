"""Video Auto-Correction Engine: Keyframe inpainting, shot regeneration, and temporal stabilization."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from engine.anime.review.render import video_encoder
from engine.inspector.repair import ImageRepairEngine
from engine.inspector.schema import (
    DefectRecord,
    InspectorConfig,
    TemporalDefectRecord,
    VideoQualityDecision,
)
from engine.inspector.temporal import TemporalVideoInspector

logger = logging.getLogger(__name__)


def _has_audio(video_path: Path) -> bool:
    """Checks whether the video contains an audio stream using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return "audio" in res.stdout.lower()
    except Exception:
        return False


def _warp_flow(img: np.ndarray, flow: np.ndarray) -> np.ndarray:
    """Warps an image using dense optical flow vectors (H, W, 2)."""
    h, w = img.shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = grid_x + flow[:, :, 0]
    map_y = grid_y + flow[:, :, 1]
    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _interpolate_motion_bidirectional(
    frame_prev: np.ndarray,
    frame_next: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """
    Interpolates an intermediate frame using bidirectional optical flow warping.
    Falls back to weighted linear blend if flow magnitude is too high or computation fails.
    """
    try:
        gray_prev = cv2.cvtColor(frame_prev, cv2.COLOR_BGR2GRAY)
        gray_next = cv2.cvtColor(frame_next, cv2.COLOR_BGR2GRAY)

        # Dense optical flow on CPU (0 MB VRAM)
        flow_fwd = cv2.calcOpticalFlowFarneback(
            gray_prev,
            gray_next,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )

        mag = np.median(np.hypot(flow_fwd[:, :, 0], flow_fwd[:, :, 1]))
        if mag > 45.0:
            # Flow too large (rapid transition or camera cut) -> fallback to linear blend
            return cv2.addWeighted(frame_prev, 1.0 - alpha, frame_next, alpha, 0)

        warped_prev = _warp_flow(frame_prev, -alpha * flow_fwd)
        warped_next = _warp_flow(frame_next, (1.0 - alpha) * flow_fwd)
        return cv2.addWeighted(warped_prev, 1.0 - alpha, warped_next, alpha, 0)
    except Exception as exc:
        logger.debug("Optical flow interpolation error (%s), using linear blend fallback", exc)
        return cv2.addWeighted(frame_prev, 1.0 - alpha, frame_next, alpha, 0)


def _extract_target_defective_frames(
    defects: List[TemporalDefectRecord],
    total_frames: int,
    fps: float,
) -> set[int]:
    """
    Extracts the exact indices of defective frames, avoiding falsely marking clean anchor frames.
    """
    defective_indices: set[int] = set()
    for defect in defects:
        if "dropped_frame" in defect.details:
            defective_indices.add(int(defect.details["dropped_frame"]))
        elif "flicker_frame" in defect.details:
            defective_indices.add(int(defect.details["flicker_frame"]))
        elif "frame" in defect.details:
            defective_indices.add(int(defect.details["frame"]))
        elif defect.category in ("flickering_limbs", "dropped_actor") and len(defect.frame_indices) == 3:
            # For 3-frame patterns (f_a, f_b, f_c), f_b is the defect, while f_a and f_c are clean anchors!
            defective_indices.add(defect.frame_indices[1])
        elif defect.frame_indices:
            defective_indices.update(defect.frame_indices)
        else:
            s_idx = max(0, int(defect.start_sec * fps))
            e_idx = min(total_frames - 1, int(defect.end_sec * fps))
            defective_indices.update(range(s_idx, e_idx + 1))
    return {i for i in defective_indices if 0 <= i < total_frames}


class VideoRepairEngine:
    """Repairs temporal inconsistencies, flickering artifacts, and defective shots in video sequences."""

    def __init__(
        self,
        config: Optional[InspectorConfig] = None,
        image_repair: Optional[ImageRepairEngine] = None,
        temporal_inspector: Optional[TemporalVideoInspector] = None,
    ):
        self.config = config or InspectorConfig()
        self.image_repair = image_repair or ImageRepairEngine()
        self.temporal_inspector = temporal_inspector or TemporalVideoInspector(config=self.config)

    def repair_video(
        self,
        video_path: str | Path,
        decision: VideoQualityDecision,
        output_dir: Optional[str | Path] = None,
        shot_generator_fn: Optional[Callable[[float, float, int], Optional[Path]]] = None,
    ) -> Tuple[Path, VideoQualityDecision, Dict[str, Any]]:
        """Executes targeted video repairs based on detected temporal defects.

        Args:
            video_path: Source input video file.
            decision: VideoQualityDecision containing detected defects.
            output_dir: Destination folder (defaults to video_path.parent / "repaired").
            shot_generator_fn: Optional callable (start_sec, end_sec, seed) -> Path of newly rendered shot.

        Returns:
            Tuple of (repaired_video_path, revalidated_decision, repair_metadata).
        """
        video_p = Path(video_path).resolve()
        if not video_p.is_file():
            raise FileNotFoundError(f"Source video not found: {video_p}")

        if decision.clean or not decision.defects:
            logger.info("Video is clean; no repairs required.")
            return video_p, decision, {"action": "none", "repaired": False}

        out_d = Path(output_dir).resolve() if output_dir else video_p.parent / "repaired"
        out_d.mkdir(parents=True, exist_ok=True)

        # Classify repair approach: frame-level inpaint vs shot-level redraw
        has_redraw_defects = any(d.recommended_action == "redraw" for d in decision.defects)
        repaired_path = out_d / f"{video_p.stem}_repaired_{uuid.uuid4().hex[:6]}.mp4"

        repair_metadata: Dict[str, Any] = {
            "original_video": str(video_p),
            "original_score": decision.overall_score,
            "defects_addressed": len(decision.defects),
            "actions_applied": [],
        }

        with tempfile.TemporaryDirectory(prefix="panelflow_vrep_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            if has_redraw_defects and shot_generator_fn is not None:
                # Shot-level regeneration path
                logger.info("Executing shot-level redraw correction with provided generator...")
                candidate_video = self._repair_by_shot_redrawing(
                    video_p, decision, tmp_path, shot_generator_fn, repair_metadata
                )
            else:
                # Frame-level inpainting and temporal stabilization path
                logger.info("Executing frame-level optical flow correction and temporal smoothing...")
                candidate_video = self._repair_by_frame_correction(
                    video_p, decision, tmp_path, repair_metadata
                )

            # Copy result to destination
            shutil.copy2(candidate_video, repaired_path)

        # Revalidation layer
        logger.info(f"Revalidating repaired video: {repaired_path.name}")
        revalidated_decision = self.temporal_inspector.inspect_video(repaired_path)

        repair_metadata["revalidated_score"] = revalidated_decision.overall_score
        repair_metadata["score_improvement"] = round(
            revalidated_decision.overall_score - decision.overall_score, 1
        )
        repair_metadata["revalidated_status"] = revalidated_decision.status
        repair_metadata["remaining_defects"] = len(revalidated_decision.defects)

        return repaired_path, revalidated_decision, repair_metadata

    def _repair_by_frame_correction(
        self,
        video_p: Path,
        decision: VideoQualityDecision,
        work_dir: Path,
        metadata: Dict[str, Any],
    ) -> Path:
        """Extracts frames, corrects defective/flickering frames via optical flow blending, and remuxes."""
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(video_p))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video for reading: {video_p}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0

        frames: List[np.ndarray] = []
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frames.append(frame)
        cap.release()

        if not frames:
            raise RuntimeError(f"No frames could be extracted from {video_p}")

        # Collect exact target frame indices to repair
        defective_indices = _extract_target_defective_frames(decision.defects, len(frames), fps)
        logger.info(f"Targeting {len(defective_indices)} defective frames out of {len(frames)} total.")

        corrected_count = 0
        for idx in sorted(defective_indices):
            # Locate closest clean keyframes on left and right
            prev_idx = idx - 1
            while prev_idx in defective_indices and prev_idx > 0:
                prev_idx -= 1

            next_idx = idx + 1
            while next_idx in defective_indices and next_idx < len(frames) - 1:
                next_idx += 1

            if 0 <= prev_idx < len(frames) and 0 <= next_idx < len(frames) and prev_idx != next_idx:
                alpha = (idx - prev_idx) / float(next_idx - prev_idx)
                blended = _interpolate_motion_bidirectional(frames[prev_idx], frames[next_idx], alpha)
                frames[idx] = blended
                corrected_count += 1
            elif 0 <= prev_idx < len(frames):
                frames[idx] = frames[prev_idx].copy()
                corrected_count += 1
            elif 0 <= next_idx < len(frames):
                frames[idx] = frames[next_idx].copy()
                corrected_count += 1

        metadata["actions_applied"].append(f"optical_flow_interpolation_{corrected_count}_frames")

        # Save corrected frames
        for i, frame in enumerate(frames):
            frame_path = frames_dir / f"frame_{i:06d}.png"
            cv2.imwrite(str(frame_path), frame)

        # Remux video using ffmpeg with audio preservation
        has_audio = _has_audio(video_p)
        out_temp = work_dir / "frame_corrected.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
        ]
        if has_audio:
            cmd.extend([
                "-i",
                str(video_p),
                *video_encoder(),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "copy",
                str(out_temp),
            ])
        else:
            cmd.extend([
                *video_encoder(),
                "-map",
                "0:v:0",
                "-an",
                str(out_temp),
            ])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out_temp.is_file():
            # Fallback without audio mapping
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frames_dir / "frame_%06d.png"),
                *video_encoder(),
                "-an",
                str(out_temp),
            ]
            res2 = subprocess.run(cmd_fallback, capture_output=True, text=True)
            if res2.returncode != 0 or not out_temp.is_file():
                raise RuntimeError(f"FFmpeg frame remux failed: {res2.stderr}")

        return out_temp

    def _repair_by_shot_redrawing(
        self,
        video_p: Path,
        decision: VideoQualityDecision,
        work_dir: Path,
        shot_generator_fn: Callable[[float, float, int], Optional[Path]],
        metadata: Dict[str, Any],
    ) -> Path:
        """Splits video around defective shots, re-renders them, and splices back together."""
        redraw_defects = [d for d in decision.defects if d.recommended_action == "redraw"]
        if not redraw_defects:
            return self._repair_by_frame_correction(video_p, decision, work_dir, metadata)

        # Merge overlapping shot intervals
        raw_intervals = sorted(
            [(max(0.0, d.start_sec), min(decision.duration_sec, d.end_sec)) for d in redraw_defects],
            key=lambda x: x[0],
        )
        merged_intervals: List[Tuple[float, float]] = []
        for s, e in raw_intervals:
            if e <= s:
                e = min(decision.duration_sec, s + 1.5)
            if not merged_intervals:
                merged_intervals.append((s, e))
            else:
                last_s, last_e = merged_intervals[-1]
                if s <= last_e:
                    merged_intervals[-1] = (last_s, max(last_e, e))
                else:
                    merged_intervals.append((s, e))

        segments: List[Path] = []
        curr_time = 0.0

        for idx, (shot_start, shot_end) in enumerate(merged_intervals):
            # 1. Clean head/interstitial cut from original video
            if shot_start - curr_time > 0.1:
                seg_head = work_dir / f"keep_{idx:02d}.mp4"
                cmd_head = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(curr_time),
                    "-to",
                    str(shot_start),
                    "-i",
                    str(video_p),
                    *video_encoder(),
                    str(seg_head),
                ]
                subprocess.run(cmd_head, capture_output=True, check=True)
                segments.append(seg_head)

            # 2. Redraw replacement shot
            seed = int(time.time()) % 1000000 + 7919 + idx * 101
            logger.info(f"Redrawing defective shot [{shot_start:.2f}s -> {shot_end:.2f}s] (seed={seed})...")
            new_shot = shot_generator_fn(shot_start, shot_end, seed)

            if new_shot and Path(new_shot).is_file():
                # Transcode new_shot to ensure matching h264 stream and timebase for concat demuxer
                seg_norm = work_dir / f"redrawn_{idx:02d}.mp4"
                cmd_norm = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(new_shot),
                    *video_encoder(),
                    str(seg_norm),
                ]
                res_norm = subprocess.run(cmd_norm, capture_output=True, text=True)
                if res_norm.returncode == 0 and seg_norm.is_file():
                    segments.append(seg_norm)
                else:
                    segments.append(Path(new_shot).resolve())
                metadata["actions_applied"].append(f"shot_redrawn_{shot_start:.2f}s_to_{shot_end:.2f}s")
            else:
                logger.warning("Shot generator failed for [%.2fs -> %.2fs]; keeping original cut.", shot_start, shot_end)
                seg_orig = work_dir / f"orig_fallback_{idx:02d}.mp4"
                cmd_orig = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(shot_start),
                    "-to",
                    str(shot_end),
                    "-i",
                    str(video_p),
                    *video_encoder(),
                    str(seg_orig),
                ]
                subprocess.run(cmd_orig, capture_output=True, check=True)
                segments.append(seg_orig)

            curr_time = shot_end

        # 3. Clean tail cut
        if decision.duration_sec - curr_time > 0.1:
            seg_tail = work_dir / "tail.mp4"
            cmd_tail = [
                "ffmpeg",
                "-y",
                "-ss",
                str(curr_time),
                "-to",
                str(decision.duration_sec),
                "-i",
                str(video_p),
                *video_encoder(),
                str(seg_tail),
            ]
            subprocess.run(cmd_tail, capture_output=True, check=True)
            segments.append(seg_tail)

        # 4. Concatenate segments
        concat_list = work_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(f"file '{seg.as_posix()}'\n")

        out_concat = work_dir / "spliced_output.mp4"
        cmd_concat = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            *video_encoder(),
            "-an",
            str(out_concat),
        ]
        res = subprocess.run(cmd_concat, capture_output=True, text=True)
        if res.returncode != 0 or not out_concat.is_file():
            logger.error(f"FFmpeg concat failed: {res.stderr}; falling back to frame correction")
            return self._repair_by_frame_correction(video_p, decision, work_dir, metadata)

        # 5. Remux original audio if available
        if _has_audio(video_p):
            final_mux = work_dir / "spliced_with_audio.mp4"
            cmd_audio = [
                "ffmpeg",
                "-y",
                "-i",
                str(out_concat),
                "-i",
                str(video_p),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-shortest",
                str(final_mux),
            ]
            res_audio = subprocess.run(cmd_audio, capture_output=True, text=True)
            if res_audio.returncode == 0 and final_mux.is_file():
                return final_mux

        return out_concat
