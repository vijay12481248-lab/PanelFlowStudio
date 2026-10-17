"""
Unit tests for MotionHasher, MotionInvalidationManager, and RepetitionDetector in engine.motion.
"""
import pytest
from engine.motion.hashing import MotionHasher
from engine.motion.planning.repetition_detector import RepetitionDetector
from engine.motion.planning.invalidation import MotionInvalidationManager
from engine.motion.models.overrides import MotionOverrides, ShotOverride
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    MasterAudioTimeline,
    AudioInterval,
    MotionStyleProfile,
)
from engine.motion.models.enums import MotionType, TimelineSourceType, WarningType
from engine.story.models import ScriptSegment, VideoScript, SegmentType


def _make_dummy_shot(shot_id: str, scene_id: str, asset_id: str, start: float, end: float, zoom: float = 1.0) -> Shot:
    return Shot(
        shot_id=shot_id,
        scene_id=scene_id,
        shot_index=0,
        source_asset_id=asset_id,
        source_image_path="/test.png",
        start_time=start,
        end_time=end,
        duration=round(end - start, 3),
        motion_type=MotionType.STATIC_HOLD,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=zoom),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=zoom),
        frame_region=NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
    )


def test_motion_hasher_deterministic():
    # Two identical MotionDirectorInputs must produce identical hash
    def build_input():
        return MotionDirectorInput(
            project_id="proj_hash",
            script=VideoScript(
                script_id="s1",
                project_id="proj_hash",
                target_duration=5.0,
                segments=[
                    ScriptSegment(
                        segment_id="seg1",
                        scene_id="sc1",
                        type=SegmentType.CHARACTER_DIALOGUE,
                        text="Line 1",
                        estimated_duration=2.0,
                    )
                ],
            ),
            master_audio_timeline=MasterAudioTimeline(
                total_duration_sec=2.5,
                timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
                intervals=[
                    AudioInterval(
                        interval_id="i1",
                        script_segment_id="seg1",
                        start_time=0.0,
                        end_time=2.5,
                        is_speech=True,
                    )
                ],
            ),
            visual_sources=[
                VisualSource(
                    asset_id="v1",
                    file_path="/p1.png",
                    width=1920,
                    height=1080,
                )
            ],
            style_profile=MotionStyleProfile(),
            seed=42,
        )

    in1 = build_input()
    in2 = build_input()

    h1 = MotionHasher.compute_input_hash(in1)
    h2 = MotionHasher.compute_input_hash(in2)
    assert h1 == h2
    assert len(h1) == 64

    # Altering a parameter changes the hash
    in3 = build_input()
    in3.seed = 43
    h3 = MotionHasher.compute_input_hash(in3)
    assert h1 != h3


def test_repetition_detector_flags_three_identical_shots():
    detector = RepetitionDetector()

    # Three identical shots in a row
    s1 = _make_dummy_shot("shot_1", "sc_1", "panel_A", 0.0, 2.0)
    s2 = _make_dummy_shot("shot_2", "sc_1", "panel_A", 2.0, 4.0)
    s3 = _make_dummy_shot("shot_3", "sc_1", "panel_A", 4.0, 6.0)

    warnings = detector.detect_repetition([s1, s2, s3], max_consecutive_identical=3)
    assert len(warnings) == 1
    assert warnings[0].warning_type == WarningType.VISUAL_REPETITION_WARNING
    assert warnings[0].shot_id == "shot_3"


def test_invalidation_manager_selective_scene_regeneration():
    inv = MotionInvalidationManager()

    s1 = _make_dummy_shot("shot_1", "sc_1", "panel_1", 0.0, 3.0)
    sc1 = MotionScene(scene_id="sc_1", sequence=1, start_time=0.0, end_time=3.0, shots=[s1])

    s2 = _make_dummy_shot("shot_2", "sc_2", "panel_2", 3.0, 6.0)
    sc2 = MotionScene(scene_id="sc_2", sequence=2, start_time=3.0, end_time=6.0, shots=[s2])

    timeline = VisualTimeline(
        project_id="proj_inv",
        total_duration_sec=6.0,
        target_resolution=TargetResolution(width=1920, height=1080),
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        scenes=[sc1, sc2],
    )

    # Invalidate scene 2 only
    stale_scenes = inv.find_stale_scene_ids_from_script(timeline, modified_scene_ids={"sc_2"})
    assert stale_scenes == {"sc_2"}
    assert "sc_1" not in stale_scenes

    # Invalidate by visual asset modification (panel_1 modified)
    stale_from_vis = inv.find_stale_scene_ids_from_visuals(timeline, modified_asset_ids={"panel_1"})
    assert stale_from_vis == {"sc_1"}
    assert "sc_2" not in stale_from_vis

    # Splice replacement for scene 2 while keeping scene 1 untouched
    replacement_s2 = _make_dummy_shot("shot_2_new", "sc_2", "panel_2_revised", 0.0, 4.0)
    replacement_sc2 = MotionScene(
        scene_id="sc_2",
        sequence=2,
        start_time=0.0,
        end_time=4.0,
        shots=[replacement_s2],
    )

    overrides = MotionOverrides()
    updated_timeline = inv.splice_regenerated_scenes(timeline, [replacement_sc2], overrides)

    assert len(updated_timeline.scenes) == 2
    assert updated_timeline.scenes[0].scene_id == "sc_1"
    assert updated_timeline.scenes[0].shots[0].shot_id == "shot_1"
    assert updated_timeline.scenes[1].scene_id == "sc_2"
    assert updated_timeline.scenes[1].shots[0].shot_id == "shot_2_new"
    # Total duration is now sc1 (3.0s) + replacement_sc2 (4.0s) = 7.0s
    assert updated_timeline.total_duration_sec == 7.0
