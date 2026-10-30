"""
Adobe After Effects Keyframe Velocity & Speed Graph Interpolator.
Translates AE's native Speed (units/sec) and Influence (%) parameters into
cubic Bezier curves, matching the After Effects Graph Editor and Keyframe Velocity dialog.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple, Optional
from engine.render.motion.curves import solve_cubic_bezier, clamp


@dataclass
class KeyframeVelocity:
    """Represents an After Effects keyframe velocity handle."""
    speed: float = 0.0          # Value units per second
    influence: float = 33.333   # Influence percentage [0.1, 100.0]

    def __post_init__(self):
        # After Effects clamps influence between 0.1% and 100%
        self.influence = max(0.1, min(100.0, float(self.influence)))
        self.speed = float(self.speed)


def ae_velocity_to_bezier(
    t0: float,
    v0: float,
    t1: float,
    v1: float,
    out_vel: KeyframeVelocity,
    in_vel: KeyframeVelocity,
) -> Tuple[float, float, float, float]:
    """
    Translates AE Keyframe Velocity (Speed + Influence) into cubic Bezier control points (x1, y1, x2, y2).
    Both x and y are normalized to [0, 1] relative to the bounding box [t0, t1] x [v0, v1].
    """
    dt = max(0.0001, t1 - t0)
    dv = v1 - v0

    # Influence directly sets horizontal control point distance
    x1 = out_vel.influence / 100.0
    x2 = 1.0 - (in_vel.influence / 100.0)

    # When delta value is practically zero (flat keyframes), control handles remain flat
    if abs(dv) < 1e-6:
        y1 = 0.0
        y2 = 1.0
    else:
        # AE vertical control point position is determined by speed * dt / dv
        y1 = (out_vel.influence / 100.0) * (out_vel.speed * dt / dv)
        y2 = 1.0 - (in_vel.influence / 100.0) * (in_vel.speed * dt / dv)

    # Clamp horizontal control points to maintain monotonic time
    x1 = clamp(x1, 0.001, 0.999)
    x2 = clamp(x2, 0.001, 0.999)

    return (x1, y1, x2, y2)


def evaluate_ae_segment(
    t: float,
    t0: float,
    v0: float,
    t1: float,
    v1: float,
    out_vel: Optional[KeyframeVelocity] = None,
    in_vel: Optional[KeyframeVelocity] = None,
) -> float:
    """
    Evaluates value at timestamp t between two After Effects keyframes (t0, v0) and (t1, v1)
    using the exact Speed + Influence Bezier parameters.
    """
    if t <= t0:
        return v0
    if t >= t1:
        return v1

    dt = max(0.0001, t1 - t0)
    norm_t = clamp((t - t0) / dt)

    o_vel = out_vel or EASY_EASE_OUT_HANDLE
    i_vel = in_vel or EASY_EASE_IN_HANDLE

    x1, y1, x2, y2 = ae_velocity_to_bezier(t0, v0, t1, v1, o_vel, i_vel)
    bezier_y = solve_cubic_bezier(norm_t, x1, y1, x2, y2)

    return v0 + (v1 - v0) * bezier_y


# ── Canonical After Effects Keyframe Velocity Presets ───────────────────────

# Standard Easy Ease (F9 in AE): 33.33% influence with 0 incoming/outgoing speed
EASY_EASE_OUT_HANDLE = KeyframeVelocity(speed=0.0, influence=33.333)
EASY_EASE_IN_HANDLE = KeyframeVelocity(speed=0.0, influence=33.333)

# Modern Tech / Hero Punchy Motion: 60% out influence, 80% in influence
AE_HERO_OUT_HANDLE = KeyframeVelocity(speed=0.0, influence=60.0)
AE_HERO_IN_HANDLE = KeyframeVelocity(speed=0.0, influence=80.0)

# Explosive Pop: 15% out influence (instant burst), 85% in influence (smooth ease-in settle)
AE_EXPLOSIVE_OUT_HANDLE = KeyframeVelocity(speed=0.0, influence=15.0)
AE_EXPLOSIVE_IN_HANDLE = KeyframeVelocity(speed=0.0, influence=85.0)

# Gentle Elegant Drift: 45% out influence, 60% in influence
AE_ELEGANT_OUT_HANDLE = KeyframeVelocity(speed=0.0, influence=45.0)
AE_ELEGANT_IN_HANDLE = KeyframeVelocity(speed=0.0, influence=60.0)
