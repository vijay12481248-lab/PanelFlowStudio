"""
Camera interpolation and easing curves evaluator for PanelFlow Motion Director.
"""
import math
from typing import Tuple
from engine.motion.models.camera import CameraState
from engine.motion.models.enums import EasingFunction


def evaluate_easing(t: float, easing: EasingFunction = EasingFunction.EASE_IN_OUT) -> float:
    """
    Evaluates normalized time t in [0.0, 1.0] across supported easing functions.
    """
    t = max(0.0, min(1.0, t))

    if easing == EasingFunction.LINEAR:
        return t

    if easing == EasingFunction.EASE_IN:
        return t * t

    if easing == EasingFunction.EASE_OUT:
        return 1.0 - (1.0 - t) * (1.0 - t)

    if easing == EasingFunction.EASE_IN_OUT:
        if t < 0.5:
            return 2.0 * t * t
        else:
            return 1.0 - math.pow(-2.0 * t + 2.0, 2) / 2.0

    if easing == EasingFunction.SMOOTHSTEP:
        # Standard Hermite smoothstep: 3t^2 - 2t^3
        return t * t * (3.0 - 2.0 * t)

    return t


def interpolate_camera(
    start: CameraState,
    end: CameraState,
    t: float,
    easing: EasingFunction = EasingFunction.EASE_IN_OUT,
) -> CameraState:
    """
    Interpolates between start and end CameraState at normalized time t in [0.0, 1.0].
    """
    factor = evaluate_easing(t, easing)

    interp_cx = start.center_x + (end.center_x - start.center_x) * factor
    interp_cy = start.center_y + (end.center_y - start.center_y) * factor
    interp_zoom = start.zoom + (end.zoom - start.zoom) * factor
    interp_rot = start.rotation + (end.rotation - start.rotation) * factor

    return CameraState(
        center_x=round(interp_cx, 4),
        center_y=round(interp_cy, 4),
        zoom=round(interp_zoom, 4),
        rotation=round(interp_rot, 2),
    )


def compute_pixel_crop_at_time(
    start: CameraState,
    end: CameraState,
    t: float,
    source_width: int,
    source_height: int,
    target_width: int = 1920,
    target_height: int = 1080,
    easing: EasingFunction = EasingFunction.EASE_IN_OUT,
) -> Tuple[int, int, int, int]:
    """
    Returns pixel (left, top, right, bottom) in source image space at time fraction t.
    """
    state_t = interpolate_camera(start, end, t, easing)
    source_aspect = source_width / max(source_height, 1)
    target_aspect = target_width / max(target_height, 1)

    vis_rect = state_t.visible_rect(target_aspect=target_aspect, source_aspect=source_aspect)
    return vis_rect.to_pixel_box(source_width, source_height)
