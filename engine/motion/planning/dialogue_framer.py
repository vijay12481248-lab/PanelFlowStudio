"""
Dialogue-aware camera framing engine.
Generates natural conversational camera paths for single-speaker and multi-speaker exchanges.
"""
from typing import Tuple, Optional
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.cues import FocusTarget
from engine.motion.models.enums import MotionType, FocusType
from engine.motion.models.input_contract import VisualSource, MotionStyleProfile
from engine.motion.camera.bounds_validator import CameraBoundsValidator


class DialogueFramer:
    """
    Computes camera start and end states for dialogue shots, balancing speaker focus and continuity.
    """

    def __init__(self):
        self.bounds_validator = CameraBoundsValidator()

    def frame_dialogue_shot(
        self,
        visual: VisualSource,
        focus_target: FocusTarget,
        style_profile: MotionStyleProfile,
        is_first_line_in_panel: bool = False,
        previous_camera_end: Optional[CameraState] = None,
        target_aspect: float = 16.0 / 9.0,
    ) -> Tuple[CameraState, CameraState, MotionType]:
        """
        Determines the camera trajectory for a dialogue shot.
        Returns (camera_start, camera_end, motion_type).
        """
        src_aspect = visual.aspect_ratio

        # 1. Speaker has an identifiable bounding box
        if focus_target.focus_type in (FocusType.SPEAKER, FocusType.CHARACTER) and focus_target.bounding_box:
            box = focus_target.bounding_box
            # Focus on upper third of character box for head/eye level
            target_cx = box.center_x
            target_cy = box.y + (box.height * 0.35)

            target_zoom = min(style_profile.max_zoom, 1.18)

            if is_first_line_in_panel:
                # Establishing move: start wider (zoom 1.02), push gently toward speaker
                c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.02)
                c_end = CameraState(center_x=target_cx, center_y=target_cy, zoom=target_zoom)
                m_type = MotionType.FOCUS_PUSH
            elif previous_camera_end and abs(previous_camera_end.center_x - target_cx) > 0.15:
                # Pan from previous speaker to current speaker
                c_start = CameraState(
                    center_x=previous_camera_end.center_x,
                    center_y=previous_camera_end.center_y,
                    zoom=target_zoom,
                )
                c_end = CameraState(center_x=target_cx, center_y=target_cy, zoom=target_zoom)
                m_type = MotionType.PAN_RIGHT if target_cx > previous_camera_end.center_x else MotionType.PAN_LEFT
            else:
                # Gentle dialogue hold / slow push
                c_start = CameraState(center_x=target_cx, center_y=target_cy, zoom=target_zoom - 0.04)
                c_end = CameraState(center_x=target_cx, center_y=target_cy, zoom=target_zoom)
                m_type = MotionType.DIALOGUE_HOLD

        else:
            # 2. Speaker location unknown: Conservative whole-panel framing with subtle push
            base_zoom = 1.0
            push_zoom = min(style_profile.max_zoom, 1.06)

            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=base_zoom)
            c_end = CameraState(center_x=0.5, center_y=0.5, zoom=push_zoom)
            m_type = MotionType.SLOW_ZOOM_IN

        # Validate and clamp both states to source bounds
        c_start, c_end, _, _ = self.bounds_validator.validate_trajectory(
            c_start, c_end, source_aspect=src_aspect, target_aspect=target_aspect
        )

        return c_start, c_end, m_type
