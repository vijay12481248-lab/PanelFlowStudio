"""
Unit tests for Adobe After Effects Expressions Engine.
"""

import math
import pytest
from engine.render.motion.ae import (
    wiggle,
    inertia_bounce,
    loop_out,
    linear,
    ease,
    value_at_time,
)


def test_wiggle_continuity_and_bounds():
    """Wiggle must produce continuous, bounded fractal noise."""
    amp = 20.0
    freq = 2.0
    for t_step in range(20):
        t = t_step * 0.1
        w = wiggle(freq=freq, amp=amp, octaves=2, t=t, seed=42)
        # Multi-octave wiggle can reach up to ~1.5x amplitude
        assert abs(w) <= amp * 2.0


def test_inertia_bounce_behavior():
    """Before keyframe, returns start value. After keyframe, creates damped oscillation around end value."""
    t_key = 1.0
    v_start = 0.0
    v_end = 100.0

    # Before keyframe arrival
    assert inertia_bounce(0.5, t_key, v_start, v_end) == 0.0

    # Right after keyframe arrival: overshoots beyond 100.0
    v_overshoot = inertia_bounce(1.05, t_key, v_start, v_end, amp=0.15, freq=4.0, decay=4.0)
    assert v_overshoot > 100.0

    # Long after keyframe arrival: settles asymptotically back to 100.0
    v_settled = inertia_bounce(3.0, t_key, v_start, v_end, amp=0.15, freq=4.0, decay=4.0)
    assert abs(v_settled - 100.0) < 0.01


def test_loop_out_cycle():
    """loopOut('cycle') should repeat the keyframe sequence continuously."""
    keys = [{"t": 0.0, "val": 10.0}, {"t": 1.0, "val": 30.0}]

    assert loop_out(keys, t_sec=0.5, loop_type="cycle") == 20.0
    # At t=1.5 (0.5s into cycle 2), value should again be 20.0
    assert loop_out(keys, t_sec=1.5, loop_type="cycle") == 20.0


def test_loop_out_pingpong():
    """loopOut('pingpong') should alternate forward and backward."""
    keys = [{"t": 0.0, "val": 0.0}, {"t": 1.0, "val": 100.0}]

    # Cycle 1 forward at t=0.5 -> 50.0
    assert abs(loop_out(keys, t_sec=0.5, loop_type="pingpong") - 50.0) < 0.1
    # Cycle 1 reverse at t=1.5 -> 50.0
    assert abs(loop_out(keys, t_sec=1.5, loop_type="pingpong") - 50.0) < 0.1
    # Cycle 1 reverse end at t=2.0 -> 0.0
    assert abs(loop_out(keys, t_sec=2.0, loop_type="pingpong") - 0.0) < 0.1


def test_loop_out_offset():
    """loopOut('offset') should accumulate the net delta each cycle."""
    keys = [{"t": 0.0, "val": 0.0}, {"t": 1.0, "val": 100.0}]

    # Cycle 1 at t=0.5 -> 50.0
    assert loop_out(keys, t_sec=0.5, loop_type="offset") == 50.0
    # Cycle 2 at t=1.5 -> 150.0
    assert loop_out(keys, t_sec=1.5, loop_type="offset") == 150.0
    # Cycle 3 at t=2.5 -> 250.0
    assert loop_out(keys, t_sec=2.5, loop_type="offset") == 250.0


def test_domain_remapping_and_value_at_time():
    """Test AE linear(), ease(), and value_at_time()."""
    assert linear(1.5, 1.0, 2.0, 0.0, 10.0) == 5.0
    assert ease(1.5, 1.0, 2.0, 0.0, 10.0) == 5.0

    evaluator = lambda t: t * 100.0
    # Delayed follower by 0.2s: at t=1.0s, evaluates at 0.8s -> 80.0
    assert value_at_time(evaluator, t=1.0, delay=0.2) == 80.0
