"""
Unit tests for MotionChoreographer: Normalized Fractional Keyframe Sequencing.
Ported from Animora Cortex (animation_templates.py).
"""

import pytest
from engine.render.motion.choreography import MotionChoreographer


def test_choreographer_initialization():
    ch = MotionChoreographer("hero_intro", duration_sec=4.0)
    assert ch.name == "hero_intro"
    assert ch.duration_sec == 4.0
    assert len(ch.keyframes) == 0


def test_duration_agnostic_scaling():
    """Keyframes at t=0.0 and t=1.0 scale proportionally across 2s, 4s, or 10s without manual edits."""
    ch = MotionChoreographer("scale_test")
    ch.add_keyframe(0.0, {"title": {"y": 100.0, "opacity": 0.0}})
    ch.add_keyframe(1.0, {"title": {"y": 0.0, "opacity": 1.0}})

    # Test at 4s duration
    eval_4s_mid = ch.evaluate_role("title", t_sec=2.0, duration_sec=4.0, easing="linear")
    assert abs(eval_4s_mid["y"] - 50.0) < 0.1
    assert abs(eval_4s_mid["opacity"] - 0.5) < 0.05

    # Test at 8s duration at the same proportional point (4s)
    eval_8s_mid = ch.evaluate_role("title", t_sec=4.0, duration_sec=8.0, easing="linear")
    assert abs(eval_8s_mid["y"] - 50.0) < 0.1
    assert abs(eval_8s_mid["opacity"] - 0.5) < 0.05


def test_multi_property_and_multi_role():
    """Verify that multiple visual elements with distinct properties are evaluated independently."""
    ch = MotionChoreographer("multi_role")
    ch.add_keyframe(0.0, {
        "badge": {"x": -200.0, "rot": -45.0},
        "headline": {"scale": 0.5, "opacity": 0.0},
    })
    ch.add_keyframe(0.5, {
        "badge": {"x": 0.0, "rot": 0.0},
        "headline": {"scale": 1.0, "opacity": 1.0},
    })
    ch.add_keyframe(1.0, {
        "badge": {"x": 10.0, "rot": 0.0},
        "headline": {"scale": 1.1, "opacity": 0.8},
    })

    # At t_sec = 2.5 of 5.0 (50% progress)
    badge_eval = ch.evaluate_role("badge", t_sec=2.5, duration_sec=5.0, easing="linear")
    assert abs(badge_eval["x"] - 0.0) < 0.1
    assert abs(badge_eval["rot"] - 0.0) < 0.1

    headline_eval = ch.evaluate_role("headline", t_sec=2.5, duration_sec=5.0, easing="linear")
    assert abs(headline_eval["scale"] - 1.0) < 0.05
    assert abs(headline_eval["opacity"] - 1.0) < 0.05


def test_looping_behavior():
    """Verify that when loop=True, evaluation wraps smoothly beyond the total duration."""
    ch = MotionChoreographer("looping_oscillator", duration_sec=2.0, loop=True)
    ch.add_keyframe(0.0, {"orb": {"x": 0.0}})
    ch.add_keyframe(0.5, {"orb": {"x": 100.0}})
    ch.add_keyframe(1.0, {"orb": {"x": 0.0}})

    # t = 1.0s is 50% through cycle 1
    cycle1 = ch.evaluate_role("orb", t_sec=1.0, easing="linear")
    assert abs(cycle1["x"] - 100.0) < 0.5

    # t = 3.0s is 50% through cycle 2
    cycle2 = ch.evaluate_role("orb", t_sec=3.0, easing="linear")
    assert abs(cycle2["x"] - 100.0) < 0.5
