"""
Unit tests for CameraBoundsValidator and camera interpolation.
"""
import pytest
from engine.motion.camera.bounds_validator import CameraBoundsValidator
from engine.motion.camera.interpolator import evaluate_easing, interpolate_camera, compute_pixel_crop_at_time
from engine.motion.camera.aspect_fitter import AspectFitter
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution
from engine.motion.models.enums import EasingFunction


def test_camera_bounds_clamping_center_and_zoom():
    validator = CameraBoundsValidator()

    # Sub-1.0 zoom (would create empty borders) should be clamped to 1.0
    bad_state = CameraState(center_x=0.0, center_y=0.0, zoom=0.5)
    clamped, modified, reason = validator.validate_and_clamp_state(bad_state, source_aspect=1.0, target_aspect=1.777)

    assert modified is True
    assert clamped.zoom >= 1.0
    assert "clamped" in reason.lower()

    # Check visible rectangle stays inside [0.0, 1.0]
    vis = clamped.visible_rect(target_aspect=1.777, source_aspect=1.0)
    assert 0.0 <= vis.x <= 1.0
    assert 0.0 <= vis.y <= 1.0
    assert vis.right <= 1.0001
    assert vis.bottom <= 1.0001


def test_camera_trajectory_validation():
    validator = CameraBoundsValidator()

    # Extreme pan attempt from far left to far right within safe frustum clamp bounds
    start = CameraState(center_x=0.05, center_y=0.5, zoom=1.2)
    end = CameraState(center_x=0.95, center_y=0.5, zoom=1.2)

    c_start, c_end, modified, reasons = validator.validate_trajectory(
        start, end, source_aspect=1.777, target_aspect=1.777
    )

    assert modified is True
    assert len(reasons) >= 2
    assert 0.0 <= c_start.center_x <= 1.0
    assert 0.0 <= c_end.center_x <= 1.0


def test_ensure_focus_visible():
    validator = CameraBoundsValidator()

    # Character located near top-right corner
    char_box = NormalizedRect(x=0.80, y=0.10, width=0.15, height=0.30)
    initial_cam = CameraState(center_x=0.20, center_y=0.50, zoom=1.3)

    adjusted = validator.ensure_focus_visible(initial_cam, char_box, source_aspect=1.0, target_aspect=1.777)

    # Camera center should have shifted toward the character
    assert adjusted.center_x > initial_cam.center_x
    assert adjusted.center_y < initial_cam.center_y


def test_easing_curves_evaluation():
    # Boundary tests for easing functions
    for easing in [EasingFunction.LINEAR, EasingFunction.EASE_IN, EasingFunction.EASE_OUT, EasingFunction.EASE_IN_OUT, EasingFunction.SMOOTHSTEP]:
        assert evaluate_easing(0.0, easing) == 0.0
        assert evaluate_easing(1.0, easing) == 1.0
        mid = evaluate_easing(0.5, easing)
        assert 0.0 <= mid <= 1.0

    # Smoothstep mid must be exactly 0.5
    assert evaluate_easing(0.5, EasingFunction.SMOOTHSTEP) == 0.5


def test_pixel_crop_computation():
    start = CameraState(center_x=0.5, center_y=0.5, zoom=1.5)
    end = CameraState(center_x=0.55, center_y=0.5, zoom=1.5)

    # Compute crop at t=0.0
    left, top, right, bottom = compute_pixel_crop_at_time(
        start, end, t=0.0, source_width=1920, source_height=1080, target_width=1920, target_height=1080
    )
    assert 0 <= left < right <= 1920
    assert 0 <= top < bottom <= 1080

    # Compute crop at t=1.0
    l1, t1, r1, b1 = compute_pixel_crop_at_time(
        start, end, t=1.0, source_width=1920, source_height=1080, target_width=1920, target_height=1080
    )
    # Right coordinate should have shifted rightwards due to center_x move
    assert l1 > left
    assert r1 > right
