"""Video Segmenter: Detects shot boundaries and cuts to extract continuous motion takes."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List

import cv2
from engine.motion_bank.ingest import probe_video
from engine.motion_bank.models import MotionSegment


HIST_SAMPLE_FPS = 10.0
HIST_STEP_THRESHOLD = 0.18   # Bhattacharyya distance between consecutive samples (0.1 s apart)
HIST_LAG_THRESHOLD = 0.30    # ... and between samples 0.5 s apart: a dissolve moves slowly but far
HIST_LAG = 5


def detect_gradual_transitions(video_path: Path, fps: float) -> List[float]:
    """
    Timestamps of dissolves, fades and soft cuts that ffmpeg's frame-to-frame scene score misses.
    Colour histograms of 10 fps samples are compared with the previous sample and with the one 0.5 s earlier;
    only local maxima over a threshold are reported.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    step = max(1, int(round(fps / HIST_SAMPLE_FPS)))
    hists: list = []
    times: List[float] = []
    i = 0
    try:
        while cap.grab():
            if i % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    small = cv2.resize(frame, (96, 96))
                    h = cv2.calcHist([cv2.cvtColor(small, cv2.COLOR_BGR2HSV)], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
                    hists.append(cv2.normalize(h, h).flatten())
                    times.append(i / fps)
            i += 1
    finally:
        cap.release()

    n = len(hists)
    d1 = [0.0] * n
    dl = [0.0] * n
    for k in range(1, n):
        d1[k] = cv2.compareHist(hists[k - 1], hists[k], cv2.HISTCMP_BHATTACHARYYA)
    for k in range(HIST_LAG, n):
        dl[k] = cv2.compareHist(hists[k - HIST_LAG], hists[k], cv2.HISTCMP_BHATTACHARYYA)

    def score(k: int) -> float:
        return max(d1[k] / HIST_STEP_THRESHOLD, dl[k] / HIST_LAG_THRESHOLD)

    cuts: List[float] = []
    for k in range(1, n):
        s = score(k)
        if s < 1.0:
            continue
        window = range(max(1, k - HIST_LAG), min(n, k + HIST_LAG + 1))
        if s >= max(score(j) for j in window):  # local maximum only
            cuts.append(times[k])
    return cuts


def detect_cuts(
    video_path: Path,
    min_duration_sec: float = 1.0,
    scene_threshold: float = 0.35,
    include_gradual: bool = True,
) -> List[MotionSegment]:
    """
    Detects shot transitions in a video: hard cuts with ffmpeg's scene filter plus (by default) dissolves and fades
    from colour-histogram differences. Returns a list of continuous takes suitable for pose harvesting.
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

    raw_cuts: List[float] = []
    # Parse showinfo output for timestamps: pts_time:12.345
    for line in r.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m:
                raw_cuts.append(float(m.group(1)))
    if include_gradual:
        raw_cuts.extend(detect_gradual_transitions(video_path, fps))

    cut_timestamps: List[float] = [0.0]
    for ts in sorted(raw_cuts):
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
