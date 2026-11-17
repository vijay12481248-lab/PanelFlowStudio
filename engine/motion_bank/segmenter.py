"""Video Segmenter: Detects shot boundaries and cuts to extract continuous motion takes."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List

from engine.motion_bank.ingest import probe_video
from engine.motion_bank.models import MotionSegment


def detect_cuts(
    video_path: Path,
    min_duration_sec: float = 1.0,
    scene_threshold: float = 0.35,
) -> List[MotionSegment]:
    """
    Detects shot transitions/cuts in a video using ffmpeg's scene filter.
    Returns a list of continuous motion takes suitable for pose harvesting.
    """
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    info = probe_video(video_path)
    total_duration = info["duration"]
    fps = info["fps"]

    # Run ffmpeg scene filter
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-filter:v", f"select='gt(scene,{scene_threshold})',showinfo",
        "-f", "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)

    cut_timestamps: List[float] = [0.0]
    # Parse showinfo output for timestamps: pts_time:12.345
    for line in r.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m:
                ts = float(m.group(1))
                if ts - cut_timestamps[-1] >= min_duration_sec:
                    cut_timestamps.append(ts)

    if total_duration - cut_timestamps[-1] >= 0.5:
        cut_timestamps.append(total_duration)
    else:
        cut_timestamps[-1] = total_duration

    segments: List[MotionSegment] = []
    for i in range(len(cut_timestamps) - 1):
        start = cut_timestamps[i]
        end = cut_timestamps[i + 1]
        dur = end - start
        if dur >= min_duration_sec:
            frames = int(round(dur * fps))
            segments.append(
                MotionSegment(
                    segment_id=f"take_{i + 1:03d}",
                    start_sec=round(start, 3),
                    end_sec=round(end, 3),
                    duration_sec=round(dur, 3),
                    fps=fps,
                    frame_count=frames,
                    score=1.0,
                )
            )

    # If no cuts were detected, the entire video is one continuous segment
    if not segments and total_duration >= min_duration_sec:
        segments.append(
            MotionSegment(
                segment_id="take_001",
                start_sec=0.0,
                end_sec=round(total_duration, 3),
                duration_sec=round(total_duration, 3),
                fps=fps,
                frame_count=int(round(total_duration * fps)),
                score=1.0,
            )
        )

    return segments
