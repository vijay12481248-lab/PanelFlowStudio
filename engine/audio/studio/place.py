"""Where a take must start so its anchor (onset or peak) lands on the cue's hit time."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Placement:
    start_s: float  # when the take begins on the timeline
    trim_s: float   # how much of the take's head to cut when the hit comes earlier than the anchor


def placement_for(hit_t: float, anchor_s: float) -> Placement:
    start = hit_t - anchor_s
    return Placement(start_s=start, trim_s=0.0) if start >= 0 else Placement(start_s=0.0, trim_s=-start)
