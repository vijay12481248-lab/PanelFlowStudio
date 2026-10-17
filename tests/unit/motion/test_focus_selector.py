"""
Unit tests for FocusSelector in engine.motion.planning.
"""
import pytest
from engine.motion.planning.focus_selector import FocusSelector
from engine.motion.models.cues import FocusTarget
from engine.motion.models.camera import NormalizedRect
from engine.motion.models.enums import FocusType, SpeechBalloonPolicy
from engine.motion.models.input_contract import VisualSource
from engine.story.models import ScriptSegment, SegmentType


def test_focus_selector_speaker_box():
    selector = FocusSelector()

    visual = VisualSource(
        asset_id="vis_01",
        file_path="/path/to/panel.png",
        width=1920,
        height=1080,
        character_bounding_boxes={
            "char_alice": NormalizedRect(x=0.1, y=0.2, width=0.3, height=0.6),
            "char_bob": NormalizedRect(x=0.6, y=0.2, width=0.3, height=0.6),
        },
    )

    seg = ScriptSegment(
        segment_id="seg_01",
        scene_id="sc_01",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="Hello world",
        speaker_character_id="char_alice",
        estimated_duration=2.0,
    )

    focus = selector.select_focus_target(visual, seg)
    assert focus.focus_type == FocusType.SPEAKER
    assert focus.character_id == "char_alice"
    assert focus.bounding_box is not None
    assert focus.bounding_box.x == 0.1
    assert focus.confidence >= 0.90


def test_focus_selector_speech_balloon():
    selector = FocusSelector()

    visual = VisualSource(
        asset_id="vis_02",
        file_path="/path/to/panel.png",
        width=1920,
        height=1080,
        character_bounding_boxes={},
        speech_balloon_boxes=[
            NormalizedRect(x=0.4, y=0.1, width=0.2, height=0.2),
        ],
    )

    seg = ScriptSegment(
        segment_id="seg_02",
        scene_id="sc_01",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="A line without bounding box",
        speaker_character_id="char_unknown",
        estimated_duration=2.0,
    )

    focus = selector.select_focus_target(visual, seg, balloon_policy=SpeechBalloonPolicy.SHOW_BALLOONS)
    assert focus.focus_type == FocusType.SPEECH_BALLOON
    assert focus.bounding_box is not None
    assert focus.bounding_box.x == 0.4


def test_focus_selector_conservative_whole_panel_fallback():
    selector = FocusSelector()

    visual = VisualSource(
        asset_id="vis_03",
        file_path="/path/to/panel.png",
        width=1920,
        height=1080,
        character_bounding_boxes={},
        speech_balloon_boxes=[],
    )

    seg = ScriptSegment(
        segment_id="seg_03",
        scene_id="sc_01",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="Mysterious voice from off-screen",
        speaker_character_id="ghost",
        estimated_duration=2.0,
    )

    focus = selector.select_focus_target(visual, seg)
    # Does NOT invent or hallucinate coordinates! Defaults conservatively to whole panel.
    assert focus.focus_type == FocusType.ENVIRONMENT_WIDE
    assert focus.character_id is None
    assert focus.bounding_box is not None
    assert focus.bounding_box.x == 0.0
    assert focus.bounding_box.y == 0.0
    assert focus.bounding_box.width == 1.0
    assert focus.bounding_box.height == 1.0
