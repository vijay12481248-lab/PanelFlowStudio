"""
Unit tests for the Newton-Raphson Cubic Bezier Engine
Ported from Animora CurveInterpolator.
"""

import math
import pytest
from engine.render.motion.curves import (
    solve_cubic_bezier,
    ease_catmull_rom,
    interpolate_value,
    BEZIER_EASE_IN_OUT,
    BEZIER_FAST_OUT_SLOW_IN,
    BEZIER_ANTICIPATE,
    BEZIER_OVERSHOOT,
)


def test_bezier_endpoints_boundary():
    """Verify that Bezier evaluation strictly pins endpoints at t=0 and t=1."""
    x1, y1, x2, y2 = BEZIER_EASE_IN_OUT
    assert solve_cubic_bezier(0.0, x1, y1, x2, y2) == 0.0
    assert solve_cubic_bezier(1.0, x1, y1, x2, y2) == 1.0
    assert solve_cubic_bezier(-0.5, x1, y1, x2, y2) == 0.0
    assert solve_cubic_bezier(1.5, x1, y1, x2, y2) == 1.0


def test_bezier_linear_diagonal():
    """A Bezier curve with diagonal control points (0.33, 0.33, 0.67, 0.67) should approximate linear."""
    for t in [0.1, 0.25, 0.5, 0.75, 0.9]:
        res = solve_cubic_bezier(t, 0.33, 0.33, 0.67, 0.67)
        assert abs(res - t) < 0.02


def test_bezier_symmetry_ease_in_out():
    """Ease-in-out curve (0.42, 0.0, 0.58, 1.0) must be point-symmetric about (0.5, 0.5)."""
    x1, y1, x2, y2 = BEZIER_EASE_IN_OUT
    mid = solve_cubic_bezier(0.5, x1, y1, x2, y2)
    assert abs(mid - 0.5) < 0.01

    val_low = solve_cubic_bezier(0.2, x1, y1, x2, y2)
    val_high = solve_cubic_bezier(0.8, x1, y1, x2, y2)
    assert abs((val_low + val_high) - 1.0) < 0.02


def test_bezier_fast_out_decel():
    """Fast-out decel curve (0.4, 0.0, 0.2, 1.0) should accelerate early."""
    x1, y1, x2, y2 = BEZIER_FAST_OUT_SLOW_IN
    val_early = solve_cubic_bezier(0.3, x1, y1, x2, y2)
    # At 30% time, fast-out progress should lead linear progress (0.30)
    assert val_early > 0.35


def test_bezier_anticipate_and_overshoot():
    """Verify anticipate dips below 0 and overshoot peaks above 1.0."""
    xa, ya, xb, yb = BEZIER_ANTICIPATE
    # Mid-anticipation should dip negative
    dip = solve_cubic_bezier(0.3, xa, ya, xb, yb)
    assert dip < 0.0

    xo1, yo1, xo2, yo2 = BEZIER_OVERSHOOT
    # Mid-overshoot should exceed 1.0
    peak = solve_cubic_bezier(0.6, xo1, yo1, xo2, yo2)
    assert peak > 1.0


def test_catmull_rom_spline():
    """Verify Catmull-Rom smooth S-curve behavior."""
    assert ease_catmull_rom(0.0) == 0.0
    assert ease_catmull_rom(1.0) == 1.0
    assert ease_catmull_rom(0.5) == 0.5
    # Smooth derivative at endpoints: slope at 0 and 1 is 0
    assert ease_catmull_rom(0.05) < 0.05
    assert ease_catmull_rom(0.95) > 0.95


def test_interpolate_value_with_bezier_curves():
    """Verify interpolate_value integrates smoothly with the registered Bezier curves."""
    res1 = interpolate_value(0.0, 100.0, 0.5, curve="bezier_ease_in_out")
    assert abs(res1 - 50.0) < 1.0

    res2 = interpolate_value(10.0, 20.0, 0.5, curve="catmull_rom")
    assert abs(res2 - 15.0) < 0.1
