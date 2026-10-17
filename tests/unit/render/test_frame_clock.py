"""
Unit tests for RenderFrameClock (Milestone 7).
Verifies rational arithmetic, frame-to-time mapping, and gapless timeline partitioning.
"""
import pytest
from engine.render.clock import RenderFrameClock


def test_frame_clock_initialization():
    clock30 = RenderFrameClock(fps=30)
    assert clock30.fps == 30

    clock60 = RenderFrameClock(fps=60)
    assert clock60.fps == 60

    with pytest.raises(ValueError):
        RenderFrameClock(fps=0)

    with pytest.raises(ValueError):
        RenderFrameClock(fps=-5)


def test_frame_to_time_exact():
    clock = RenderFrameClock(fps=30)
    assert clock.frame_to_time(0) == 0.0
    assert clock.frame_to_time(15) == 0.5
    assert clock.frame_to_time(30) == 1.0
    assert clock.frame_to_time(90) == 3.0


def test_time_to_frame_rounding():
    clock = RenderFrameClock(fps=30)
    assert clock.time_to_frame(0.0) == 0
    assert clock.time_to_frame(-1.0) == 0
    assert clock.time_to_frame(1.0) == 30
    assert clock.time_to_frame(0.5) == 15
    assert clock.time_to_frame(0.033333) == 1


def test_time_range_to_frame_range_partitioning():
    clock = RenderFrameClock(fps=30)

    # Contiguous intervals
    ranges = [
        (0.0, 2.5),
        (2.5, 5.1),
        (5.1, 7.8),
    ]

    prev_end = None
    accumulated_frames = 0
    for s_sec, e_sec in ranges:
        start_frame, end_frame, count = clock.time_range_to_frame_range(s_sec, e_sec)
        assert end_frame > start_frame
        assert count == end_frame - start_frame
        if prev_end is not None:
            # Guarantees zero gaps and zero overlaps between contiguous segments
            assert start_frame == prev_end
        prev_end = end_frame
        accumulated_frames += count

    expected_total = clock.time_to_frame(7.8)
    assert accumulated_frames == expected_total


def test_normalized_progress():
    clock = RenderFrameClock(fps=30)
    start_frame = 30
    end_frame = 60  # 30 frames: frames 30 to 59

    # Start of shot
    p_start = clock.normalized_progress(30, start_frame, end_frame)
    assert p_start == 0.0

    # End of shot
    p_end = clock.normalized_progress(59, start_frame, end_frame)
    assert p_end == 1.0

    # Midpoint
    p_mid = clock.normalized_progress(45, start_frame, end_frame)
    assert pytest.approx(p_mid, abs=0.05) == 0.517

    # Single-frame degenerate shot
    p_deg = clock.normalized_progress(10, 10, 11)
    assert p_deg == 0.0 or p_deg == 1.0
