"""
Unit tests for DialogueFramer in engine.motion.planning.
"""
import pytest
from engine.motion.planning.dialogue_framer import DialogueFramer
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.cues import FocusTarget
from engine.motion.models.enums import MotionType, FocusType
from engine.motion.models.input_contract import VisualSource, MotionStyleProfile


def test_dialogue_framer_first_line_establishing_push():
    framer = DialogueFramer()
    style = MotionStyleProfile()

    visual = VisualSource(
        asset_id="v1",
        file_path="/dummy.png",
        width=1920,
        height=1080,
    )

    focus = FocusTarget(
        focus_type=FocusType.SPEAKER,
        character_id="alice",
        bounding_box=NormalizedRect(x=0.2, y=0.3, width=0.2, height=0.4),
    )

    start_cam, end_cam, m_type = framer.frame_dialogue_shot(
        visual, focus, style, is_first_line_in_panel=True, target_aspect=1.777
    )

    # First line in panel should do FOCUS_PUSH starting wider
    assert m_type == MotionType.FOCUS_PUSH
    assert end_cam.zoom >= start_cam.zoom


def test_dialogue_framer_two_speaker_pan():
    framer = DialogueFramer()
    style = MotionStyleProfile()

    visual = VisualSource(
        asset_id="v1",
        file_path="/dummy.png",
        width=1920,
        height=1080,
    )

    # Speaker B is on the right side of the panel
    focus_b = FocusTarget(
        focus_type=FocusType.SPEAKER,
        character_id="bob",
        bounding_box=NormalizedRect(x=0.7, y=0.3, width=0.2, height=0.4),
    )

    # Previous camera was focused on Alice on the left side (center_x = 0.3)
    prev_cam = CameraState(center_x=0.3, center_y=0.4, zoom=1.15)

    start_cam, end_cam, m_type = framer.frame_dialogue_shot(
        visual, focus_b, style, is_first_line_in_panel=False, previous_camera_end=prev_cam, target_aspect=1.777
    )

    # Transitioning from left (0.3) to right (0.8) should trigger PAN_RIGHT
    assert m_type == MotionType.PAN_RIGHT
    assert end_cam.center_x > start_cam.center_x


def test_dialogue_framer_dialogue_hold():
    framer = DialogueFramer()
    style = MotionStyleProfile()

    visual = VisualSource(
        asset_id="v1",
        file_path="/dummy.png",
        width=1920,
        height=1080,
    )

    # Consecutive line by same speaker
    focus_alice = FocusTarget(
        focus_type=FocusType.SPEAKER,
        character_id="alice",
        bounding_box=NormalizedRect(x=0.2, y=0.3, width=0.2, height=0.4),
    )

    prev_cam = CameraState(center_x=0.3, center_y=0.4, zoom=1.15)

    start_cam, end_cam, m_type = framer.frame_dialogue_shot(
        visual, focus_alice, style, is_first_line_in_panel=False, previous_camera_end=prev_cam, target_aspect=1.777
    )

    assert m_type == MotionType.DIALOGUE_HOLD


def test_dialogue_framer_fallback_wide():
    framer = DialogueFramer()
    style = MotionStyleProfile()

    visual = VisualSource(
        asset_id="v1",
        file_path="/dummy.png",
        width=1920,
        height=1080,
    )

    # Unknown focus
    focus = FocusTarget.whole_panel("Unknown character")

    start_cam, end_cam, m_type = framer.frame_dialogue_shot(
        visual, focus, style, is_first_line_in_panel=False, target_aspect=1.777
    )

    assert m_type == MotionType.SLOW_ZOOM_IN
    assert start_cam.center_x == 0.5
    assert end_cam.center_x == 0.5
