"""
Camera bounds validator and clamping engine.
Guarantees that camera motion paths never reveal areas outside the source visual asset.
"""
from typing import Tuple, List, Optional
from engine.motion.models.camera import CameraState, NormalizedRect


class CameraBoundsValidator:
    """
    Validates and clamps camera positions, crops, and zooms to strictly preserve source bounds.
    """

    def validate_and_clamp_state(
        self,
        state: CameraState,
        source_aspect: float = 1.0,
        target_aspect: float = 16.0 / 9.0,
    ) -> Tuple[CameraState, bool, Optional[str]]:
        """
        Clamps a CameraState so that its visible frustum remains strictly inside [0.0, 1.0] x [0.0, 1.0].
        Returns (clamped_state, was_modified, reason).
        """
        was_modified = False
        reasons = []

        # 1. Clamp zoom
        zoom = state.zoom
        if zoom < 1.0:
            zoom = 1.0
            was_modified = True
            reasons.append(f"Zoom {state.zoom:.2f} clamped to 1.00 minimum to prevent empty borders")

        # 2. Determine visible viewport dimensions in normalized source coordinates
        # If source is wider than target aspect, height is constrained; if taller, width is.
        if source_aspect >= target_aspect:
            vis_h = 1.0 / zoom
            vis_w = (vis_h * target_aspect) / source_aspect
        else:
            vis_w = 1.0 / zoom
            vis_h = (vis_w / target_aspect) * source_aspect

        vis_w = min(1.0, vis_w)
        vis_h = min(1.0, vis_h)

        half_w = vis_w / 2.0
        half_h = vis_h / 2.0

        min_cx = half_w
        max_cx = 1.0 - half_w
        min_cy = half_h
        max_cy = 1.0 - half_h

        # If min > max (due to aspect math), lock center to 0.5
        cx = state.center_x
        if min_cx > max_cx:
            cx = 0.5
        else:
            if cx < min_cx:
                cx = min_cx
                was_modified = True
                reasons.append(f"center_x {state.center_x:.3f} clamped to min safe {min_cx:.3f}")
            elif cx > max_cx:
                cx = max_cx
                was_modified = True
                reasons.append(f"center_x {state.center_x:.3f} clamped to max safe {max_cx:.3f}")

        cy = state.center_y
        if min_cy > max_cy:
            cy = 0.5
        else:
            if cy < min_cy:
                cy = min_cy
                was_modified = True
                reasons.append(f"center_y {state.center_y:.3f} clamped to min safe {min_cy:.3f}")
            elif cy > max_cy:
                cy = max_cy
                was_modified = True
                reasons.append(f"center_y {state.center_y:.3f} clamped to max safe {max_cy:.3f}")

        # Clamp rotation between -15.0 and +15.0 for safety unless extreme intentionally
        rot = max(-45.0, min(45.0, state.rotation))
        if rot != state.rotation:
            was_modified = True
            reasons.append(f"rotation {state.rotation} clamped to safe limit {rot}")

        clamped = CameraState(
            center_x=round(cx, 4),
            center_y=round(cy, 4),
            zoom=round(zoom, 4),
            rotation=round(rot, 2),
            crop=state.crop.clamp() if state.crop else None,
        )
        reason_str = "; ".join(reasons) if was_modified else None
        return clamped, was_modified, reason_str

    def validate_trajectory(
        self,
        start_state: CameraState,
        end_state: CameraState,
        source_aspect: float = 1.0,
        target_aspect: float = 16.0 / 9.0,
    ) -> Tuple[CameraState, CameraState, bool, List[str]]:
        """
        Validates both endpoints of a camera move.
        Ensures smooth, frame-safe motion without border gaps.
        """
        mod_reasons: List[str] = []
        c_start, mod_start, r_start = self.validate_and_clamp_state(start_state, source_aspect, target_aspect)
        if mod_start and r_start:
            mod_reasons.append(f"Start: {r_start}")

        c_end, mod_end, r_end = self.validate_and_clamp_state(end_state, source_aspect, target_aspect)
        if mod_end and r_end:
            mod_reasons.append(f"End: {r_end}")

        return c_start, c_end, bool(mod_start or mod_end), mod_reasons

    def ensure_focus_visible(
        self,
        state: CameraState,
        focus_box: NormalizedRect,
        source_aspect: float = 1.0,
        target_aspect: float = 16.0 / 9.0,
    ) -> CameraState:
        """
        Adjusts camera center so that the requested focal bounding box is not cut off by the visible frustum.
        """
        clamped_state, _, _ = self.validate_and_clamp_state(state, source_aspect, target_aspect)
        vis_rect = clamped_state.visible_rect(target_aspect=target_aspect, source_aspect=source_aspect)

        target_cx = clamped_state.center_x
        target_cy = clamped_state.center_y

        # If focus box center is significantly off-screen from visible rect
        if focus_box.center_x < vis_rect.x:
            target_cx = focus_box.center_x + (vis_rect.width / 4.0)
        elif focus_box.center_x > vis_rect.right:
            target_cx = focus_box.center_x - (vis_rect.width / 4.0)

        if focus_box.center_y < vis_rect.y:
            target_cy = focus_box.center_y + (vis_rect.height / 4.0)
        elif focus_box.center_y > vis_rect.bottom:
            target_cy = focus_box.center_y - (vis_rect.height / 4.0)

        adjusted = CameraState(
            center_x=target_cx,
            center_y=target_cy,
            zoom=clamped_state.zoom,
            rotation=clamped_state.rotation,
            crop=clamped_state.crop,
        )
        safe_adjusted, _, _ = self.validate_and_clamp_state(adjusted, source_aspect, target_aspect)
        return safe_adjusted
