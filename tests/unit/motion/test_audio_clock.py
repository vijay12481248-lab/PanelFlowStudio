"""
Unit tests for AudioClockResolver in engine.motion.timing.
"""
import pytest
from engine.motion.timing.audio_clock import AudioClockResolver
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval
from engine.motion.models.enums import TimelineSourceType
from engine.story.models import ScriptSegment, VideoScript, SegmentType


def test_audio_clock_exact_segment_locking():
    resolver = AudioClockResolver()

    # Create dummy script
    seg1 = ScriptSegment(
        segment_id="seg_01",
        scene_id="sc_01",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="Hello world.",
        speaker_character_id="char_alice",
        estimated_duration=2.0,
    )
    seg2 = ScriptSegment(
        segment_id="seg_02",
        scene_id="sc_01",
        type=SegmentType.CHARACTER_DIALOGUE,
        text="Greetings Alice.",
        speaker_character_id="char_bob",
        estimated_duration=2.5,
    )
    script = VideoScript(
        script_id="scr_01",
        project_id="proj_01",
        target_duration=10.0,
        segments=[seg1, seg2],
    )

    # Master timeline with exact audio speech durations
    timeline = MasterAudioTimeline(
        total_duration_sec=6.5,
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        intervals=[
            AudioInterval(
                interval_id="iv_01",
                script_segment_id="seg_01",
                speaker_character_id="char_alice",
                start_time=0.5,
                end_time=2.8,
                is_speech=True,
            ),
            AudioInterval(
                interval_id="iv_02",
                script_segment_id="seg_02",
                speaker_character_id="char_bob",
                start_time=3.3,
                end_time=6.2,
                is_speech=True,
            ),
        ],
    )

    pairs = resolver.resolve_timeline_intervals(script, timeline)
    assert len(pairs) == 2

    s1, a1 = pairs[0]
    assert s1.segment_id == "seg_01"
    assert a1.start_time == 0.5
    assert a1.end_time == 2.8

    s2, a2 = pairs[1]
    assert s2.segment_id == "seg_02"
    assert a2.start_time == 3.3
    assert a2.end_time == 6.2


def test_audio_clock_pause_detection():
    resolver = AudioClockResolver()

    intervals = [
        AudioInterval(
            interval_id="iv_01",
            start_time=0.0,
            end_time=2.0,
            is_speech=True,
        ),
        AudioInterval(
            interval_id="iv_02",
            start_time=3.0,
            end_time=5.0,
            is_speech=True,
        ),
        AudioInterval(
            interval_id="iv_03",
            start_time=5.2,
            end_time=7.0,
            is_speech=True,
        ),
    ]

    pauses = resolver.detect_pauses_and_gaps(intervals, min_pause_sec=0.4)
    # Between iv_01 and iv_02 there is 1.0s gap (>= 0.4s) -> should be detected
    # Between iv_02 and iv_03 there is 0.2s gap (< 0.4s) -> should not be detected
    assert len(pauses) == 1
    assert pauses[0] == (2.0, 3.0)


def test_audio_clock_fixture_provenance():
    timeline = MasterAudioTimeline(
        total_duration_sec=5.0,
        timeline_source=TimelineSourceType.DEVELOPMENT_TIMELINE_FIXTURE,
        intervals=[],
    )
    assert timeline.timeline_source == TimelineSourceType.DEVELOPMENT_TIMELINE_FIXTURE
