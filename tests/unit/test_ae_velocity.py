"""
Unit tests for Adobe After Effects Keyframe Velocity & Speed Graph Interpolator.
"""

import pytest
from engine.render.motion.ae import (
    KeyframeVelocity,
    ae_velocity_to_bezier,
    evaluate_ae_segment,
    EASY_EASE_OUT_HANDLE,
    EASY_EASE_IN_HANDLE,
    AE_HERO_OUT_HANDLE,
    AE_HERO_IN_HANDLE,
    AE_EXPLOSIVE_OUT_HANDLE,
    AE_EXPLOSIVE_IN_HANDLE,
)


def test_keyframe_velocity_clamping():
    """Verify influence is clamped to [0.1, 100.0] matching AE dialog constraints."""
    v1 = KeyframeVelocity(speed=150.0, influence=0.0)
    assert v1.influence == 0.1

    v2 = KeyframeVelocity(speed=-50.0, influence=120.0)
    assert v2.influence == 100.0

    v3 = KeyframeVelocity(speed=0.0, influence=75.0)
    assert v3.influence == 75.0
    assert v3.speed == 0.0


def test_easy_ease_bezier_conversion():
    """Easy Ease (F9): 33.333% out/in with 0 speed should produce symmetric S-curve."""
    x1, y1, x2, y2 = ae_velocity_to_bezier(
        t0=0.0, v0=0.0, t1=1.0, v1=100.0,
        out_vel=EASY_EASE_OUT_HANDLE,
        in_vel=EASY_EASE_IN_HANDLE,
    )
    assert abs(x1 - 0.333) < 0.01
    assert abs(x2 - 0.667) < 0.01
    assert y1 == 0.0
    assert y2 == 1.0


def test_ae_hero_punchy_motion_evaluation():
    """AE 60%/80% Hero curve should produce a sharp initial acceleration with smooth settle."""
    v_mid = evaluate_ae_segment(
        t=0.5, t0=0.0, v0=0.0, t1=1.0, v1=100.0,
        out_vel=AE_HERO_OUT_HANDLE,
        in_vel=AE_HERO_IN_HANDLE,
    )
    # At 50% time, hero motion should have covered over 70% of travel
    assert v_mid > 70.0
    assert v_mid < 100.0


def test_ae_explosive_pop():
    """15% out / 85% in explosive pop handle should cover >60% travel by t=0.3s."""
    v_early = evaluate_ae_segment(
        t=0.3, t0=0.0, v0=0.0, t1=1.0, v1=100.0,
        out_vel=AE_EXPLOSIVE_OUT_HANDLE,
        in_vel=AE_EXPLOSIVE_IN_HANDLE,
    )
    assert v_early > 60.0


def test_ae_segment_boundaries():
    """Values before t0 or after t1 must clamp exactly to keyframe bounds."""
    val_before = evaluate_ae_segment(t=-0.5, t0=0.0, v0=10.0, t1=2.0, v1=50.0)
    assert val_before == 10.0

    val_after = evaluate_ae_segment(t=3.0, t0=0.0, v0=10.0, t1=2.0, v1=50.0)
    assert val_after == 50.0
