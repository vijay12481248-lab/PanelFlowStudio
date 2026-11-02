"""Clip selection: one short clip per beat, snapped to shot boundaries, inside a footage budget."""
from __future__ import annotations

import numpy as np

from engine.anime.review.models import Beat, Clip, ClipPlan, EpisodeAnalysis

MAX_CLIP_SEC = 20.0
MIN_CLIP_SEC = 1.5
DEFAULT_CLIP_SEC = 7.0
SOURCE_FRACTION = 0.20  # never reuse more than this share of the episode
VIDEO_FRACTION = 0.25   # nor more than this share of the final review
LOUD_KINDS = {"highlight", "emotional", "funny"}
ESSENTIAL_KINDS = {"opening", "highlight", "ending"}


def budget_sec(source_sec: float, target_video_sec: float) -> float:
    return min(source_sec * SOURCE_FRACTION, target_video_sec * VIDEO_FRACTION)


def _energy(rms: np.ndarray, a: float, b: float) -> float:
    seg = rms[int(a): max(int(b), int(a) + 1)]
    return float(seg.mean()) if seg.size else 0.0


def _candidates(a: EpisodeAnalysis, b: Beat, clip_sec: float) -> list[tuple[float, float]]:
    """Each shot overlapping the beat yields a window starting at the shot (or beat) start."""
    out = []
    for s in a.shots:
        if s.end <= b.start or s.start >= b.end:
            continue
        start = max(s.start, b.start)
        end = min(start + clip_sec, b.end)
        if end - start >= MIN_CLIP_SEC:
            out.append((start, end))
    return out


def select_clips(a: EpisodeAnalysis, beats: list[Beat], target_video_sec: float,
                 rms: np.ndarray | None = None, clip_sec: float = DEFAULT_CLIP_SEC) -> ClipPlan:
    budget = budget_sec(a.duration_sec, target_video_sec)
    clip_sec = min(clip_sec, MAX_CLIP_SEC)
    rms = rms if rms is not None else np.zeros(0)
    used = 0.0
    chosen: dict[str, Clip] = {}
    dropped: list[str] = []
    # essential beats first so a tight budget still covers the story; the rest follow in time order
    for b in sorted(beats, key=lambda b: (b.kind not in ESSENTIAL_KINDS, b.start)):
        cands = _candidates(a, b, clip_sec)
        if not cands:
            dropped.append(b.id)
            continue
        start, end = max(cands, key=lambda c: _energy(rms, *c)) if b.kind in LOUD_KINDS and rms.size else cands[0]
        length = min(end - start, budget - used)
        if length < MIN_CLIP_SEC:
            dropped.append(b.id)
            continue
        used += length
        chosen[b.id] = Clip(id="", beat_id=b.id, start=round(start, 3), end=round(start + length, 3), purpose=b.label)
    clips = []
    for b in beats:  # time order, stable ids
        if b.id in chosen:
            clips.append(chosen[b.id].model_copy(update={"id": f"c{len(clips) + 1:02d}"}))
    return ClipPlan(clips=clips, total_sec=round(sum(c.duration for c in clips), 2),
                    budget_sec=round(budget, 2), dropped_beats=dropped)
