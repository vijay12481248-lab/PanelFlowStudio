"""Motion curves and easing math for After Effects-grade procedural animation."""

from __future__ import annotations

import math
from typing import Callable, Dict, Any


def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))


def ease_linear(t: float) -> float:
    return clamp(t)


def ease_in_quad(t: float) -> float:
    t = clamp(t)
    return t * t


def ease_out_quad(t: float) -> float:
    t = clamp(t)
    return t * (2.0 - t)


def ease_in_out_quad(t: float) -> float:
    t = clamp(t)
    return 2.0 * t * t if t < 0.5 else -1.0 + (4.0 - 2.0 * t) * t


def ease_in_cubic(t: float) -> float:
    t = clamp(t)
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - math.pow(1.0 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4.0 * t * t * t if t < 0.5 else (t - 1.0) * (2.0 * t - 2.0) * (2.0 * t - 2.0) + 1.0


def ease_in_quart(t: float) -> float:
    t = clamp(t)
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    t = clamp(t)
    return 1.0 - math.pow(1.0 - t, 4)


def ease_in_out_quart(t: float) -> float:
    t = clamp(t)
    return 8.0 * t * t * t * t if t < 0.5 else 1.0 - 8.0 * math.pow(t - 1.0, 4)


def ease_in_expo(t: float) -> float:
    t = clamp(t)
    return 0.0 if t <= 0.0 else math.pow(2.0, 10.0 * (t - 1.0))


def ease_out_expo(t: float) -> float:
    t = clamp(t)
    return 1.0 if t >= 1.0 else 1.0 - math.pow(2.0, -10.0 * t)


def ease_in_out_expo(t: float) -> float:
    t = clamp(t)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 0.5 * math.pow(2.0, (20.0 * t) - 10.0)
    return 1.0 - 0.5 * math.pow(2.0, (-20.0 * t) + 10.0)


def ease_out_back(t: float, s: float = 1.4) -> float:
    """Over-shooting cubic easing that creates snappy spring pop-in."""
    t = clamp(t)
    return 1.0 + (s + 1.0) * math.pow(t - 1.0, 3) + s * math.pow(t - 1.0, 2)


def ease_in_back(t: float, s: float = 1.4) -> float:
    t = clamp(t)
    return t * t * ((s + 1.0) * t - s)


def ease_in_out_back(t: float, s: float = 1.4) -> float:
    t = clamp(t)
    s2 = s * 1.525
    t2 = t * 2.0
    if t2 < 1.0:
        return 0.5 * (t2 * t2 * ((s2 + 1.0) * t2 - s2))
    t2 -= 2.0
    return 0.5 * (t2 * t2 * ((s2 + 1.0) * t2 + s2) + 2.0)


def ease_out_elastic(t: float, p: float = 0.3) -> float:
    """Organic elastic jelly spring curve."""
    t = clamp(t)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    s = p / 4.0
    return math.pow(2.0, -10.0 * t) * math.sin((t - s) * (2.0 * math.pi) / p) + 1.0


def spring_interpolate(t: float, stiffness: float = 100.0, damping: float = 12.0) -> float:
    """Underdamped spring step response for natural UI physical motion."""
    t = clamp(t)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    omega = math.sqrt(max(1.0, stiffness))
    zeta = damping / (2.0 * omega)
    if zeta < 1.0:
        omega_d = omega * math.sqrt(1.0 - zeta * zeta)
        decay = math.exp(-zeta * omega * t)
        return 1.0 - decay * (math.cos(omega_d * t) + (zeta / math.sqrt(1.0 - zeta * zeta)) * math.sin(omega_d * t))
    return ease_out_cubic(t)


# ── Newton-Raphson Cubic Bezier Engine (Ported from Animora) ───────────────

NEWTON_RAPHSON_ITERATIONS = 8
NEWTON_RAPHSON_TOLERANCE = 0.001
DERIVATIVE_MINIMUM = 0.0001


def _cubic_bezier_comp(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1.0 - t
    return u * u * u * p0 + 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t * p3


def _cubic_bezier_deriv(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * (p1 - p0) + 6.0 * u * t * (p2 - p1) + 3.0 * t * t * (p3 - p2)


def solve_cubic_bezier(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Evaluates cubic Bezier curve easing factor via Newton-Raphson iteration.
    Matches CSS cubic-bezier, Adobe After Effects, Spine, and Animora CurveInterpolator.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    bezier_t = t
    for _ in range(NEWTON_RAPHSON_ITERATIONS):
        x = _cubic_bezier_comp(bezier_t, 0.0, x1, x2, 1.0) - t
        if abs(x) < NEWTON_RAPHSON_TOLERANCE:
            break
        dx = _cubic_bezier_deriv(bezier_t, 0.0, x1, x2, 1.0)
        if abs(dx) < DERIVATIVE_MINIMUM:
            break
        bezier_t -= x / dx

    bezier_t = max(0.0, min(1.0, bezier_t))
    return _cubic_bezier_comp(bezier_t, 0.0, y1, y2, 1.0)


def ease_catmull_rom(t: float) -> float:
    """Catmull-Rom cubic spline approximation (smooth S-curve)."""
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


# Standard Production Bezier Presets
BEZIER_EASE = (0.25, 0.1, 0.25, 1.0)
BEZIER_EASE_IN = (0.42, 0.0, 1.0, 1.0)
BEZIER_EASE_OUT = (0.0, 0.0, 0.58, 1.0)
BEZIER_EASE_IN_OUT = (0.42, 0.0, 0.58, 1.0)
BEZIER_FAST_OUT_SLOW_IN = (0.4, 0.0, 0.2, 1.0)
BEZIER_ANTICIPATE = (0.36, 0.0, 0.66, -0.56)
BEZIER_OVERSHOOT = (0.34, 1.56, 0.64, 1.0)


EASING_MAP: Dict[str, Callable[[float], float]] = {
    "spline": ease_catmull_rom,
    "catmull_rom": ease_catmull_rom,
    "bezier_ease": lambda t: solve_cubic_bezier(t, 0.25, 0.1, 0.25, 1.0),
    "bezier_ease_in_out": lambda t: solve_cubic_bezier(t, 0.42, 0.0, 0.58, 1.0),
    "bezier_fast_out": lambda t: solve_cubic_bezier(t, 0.4, 0.0, 0.2, 1.0),
    "linear": ease_linear,
    "ease_in": ease_in_cubic,
    "ease_out": ease_out_cubic,
    "ease_in_out": ease_in_out_cubic,
    "ease_out_quad": ease_out_quad,
    "ease_out_cubic": ease_out_cubic,
    "ease_out_quart": ease_out_quart,
    "ease_out_expo": ease_out_expo,
    "ease_out_back": ease_out_back,
    "ease_in_back": ease_in_back,
    "ease_in_out_back": ease_in_out_back,
    "ease_out_elastic": ease_out_elastic,
    "spring": spring_interpolate,
}


def interpolate_value(
    start: float,
    end: float,
    progress: float,
    curve: str = "ease_out_cubic",
    **kwargs: Any,
) -> float:
    """Interpolate between start and end using the designated easing curve."""
    p = clamp(progress)
    fn = EASING_MAP.get(curve, ease_out_cubic)
    eased = fn(p) if not kwargs else (ease_out_back(p, kwargs["s"]) if curve == "ease_out_back" and "s" in kwargs else fn(p))
    return start + (end - start) * eased
