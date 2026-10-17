"""
Unit tests for TimingDirector in engine.motion.timing.
"""
import pytest
from engine.motion.timing.duration_rules import TimingDirector
from engine.motion.models.input_contract import MotionStyleProfile
from engine.story.models import ScriptSegment, SegmentType


def test_timing_director_minimum_shot_duration():
    director = TimingDirector()
    style = MotionStyleProfile(min_shot_duration=2.0)

    seg = ScriptSegment(
        segment_id="s1",
        scene_id="sc1",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="Hi",
        estimated_duration=0.8,
    )

    # Audio is very brief (0.8s), but should be bounded by min_shot_duration (2.0s)
    dur = director.calculate_ideal_duration(audio_duration=0.8, segment=seg, style_profile=style)
    assert dur >= 2.0


def test_timing_director_establishing_shot_duration():
    director = TimingDirector()
    style = MotionStyleProfile(establishing_shot_duration=3.5)

    seg = ScriptSegment(
        segment_id="s2",
        scene_id="sc1",
        type=SegmentType.NARRATOR,
        text="The ancient gates stood still.",
        estimated_duration=1.5,
    )

    dur = director.calculate_ideal_duration(audio_duration=1.5, segment=seg, is_establishing=True, style_profile=style)
    assert dur >= 3.5


def test_timing_director_should_merge_adjacent_shots():
    director = TimingDirector()
    style = MotionStyleProfile(min_shot_duration=2.0, comfortable_dialogue_max=8.0)

    seg_a = ScriptSegment(segment_id="sa", scene_id="sc1", type=SegmentType.CHARACTER_DIALOGUE, text="Wait.")
    seg_b = ScriptSegment(segment_id="sb", scene_id="sc1", type=SegmentType.CHARACTER_DIALOGUE, text="Did you hear that?")

    # Same panel, short first line (1.2s < min 2.0s), combined 4.2s <= 8.0s -> merge!
    should_merge = director.should_merge_adjacent_shots(
        seg_a=seg_a,
        seg_b=seg_b,
        source_id_a="panel_1",
        source_id_b="panel_1",
        dur_a=1.2,
        dur_b=3.0,
        style_profile=style,
    )
    assert should_merge is True

    # Different panels -> never merge
    should_not_merge = director.should_merge_adjacent_shots(
        seg_a=seg_a,
        seg_b=seg_b,
        source_id_a="panel_1",
        source_id_b="panel_2",
        dur_a=1.2,
        dur_b=3.0,
        style_profile=style,
    )
    assert should_not_merge is False
