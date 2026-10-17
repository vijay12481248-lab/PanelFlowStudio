"""
Unit tests for CompositionValidator in engine.motion.validation.
"""
import pytest
from engine.motion.validation.composition_validator import CompositionValidator
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution
from engine.motion.models.enums import MotionType, WarningType, WarningSeverity, TimelineSourceType


def _make_dummy_shot(shot_id: str, start_time: float, end_time: float, asset_id: str = "asset_1") -> Shot:
    return Shot(
        shot_id=shot_id,
        scene_id="scene_1",
        shot_index=0,
        source_asset_id=asset_id,
        source_image_path="/path/to/asset.png",
        start_time=start_time,
        end_time=end_time,
        duration=round(end_time - start_time, 3),
        motion_type=MotionType.STATIC_HOLD,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        frame_region=NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
    )


def test_validator_clean_timeline():
    validator = CompositionValidator()

    s1 = _make_dummy_shot("s1", 0.0, 3.0)
    s2 = _make_dummy_shot("s2", 3.0, 6.0)

    scene = MotionScene(
        scene_id="sc_1",
        scene_index=0,
        start_time=0.0,
        end_time=6.0,
        duration=6.0,
        shots=[s1, s2],
    )

    timeline = VisualTimeline(
        project_id="proj_1",
        total_duration_sec=6.0,
        target_resolution=TargetResolution(width=1920, height=1080),
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        scenes=[scene],
    )

    is_valid, warnings = validator.validate_timeline(timeline, known_visual_asset_ids=["asset_1"])
    assert is_valid is True
    # Should have no ERROR warnings
    assert not any(w.severity == WarningSeverity.ERROR for w in warnings)


def test_validator_detects_gap():
    validator = CompositionValidator()

    # Gap of 0.5s between 3.0s and 3.5s
    s1 = _make_dummy_shot("s1", 0.0, 3.0)
    s2 = _make_dummy_shot("s2", 3.5, 6.0)

    scene = MotionScene(
        scene_id="sc_1",
        scene_index=0,
        start_time=0.0,
        end_time=6.0,
        duration=6.0,
        shots=[s1, s2],
    )

    timeline = VisualTimeline(
        project_id="proj_1",
        total_duration_sec=6.0,
        target_resolution=TargetResolution(width=1920, height=1080),
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        scenes=[scene],
    )

    is_valid, warnings = validator.validate_timeline(timeline)
    assert is_valid is False
    assert any(w.warning_type == WarningType.VISUAL_TIMELINE_GAP for w in warnings)


def test_validator_detects_overlap():
    validator = CompositionValidator()

    # Overlap of 0.5s: s1 ends at 3.5s, s2 starts at 3.0s
    s1 = _make_dummy_shot("s1", 0.0, 3.5)
    s2 = _make_dummy_shot("s2", 3.0, 6.0)

    scene = MotionScene(
        scene_id="sc_1",
        scene_index=0,
        start_time=0.0,
        end_time=6.0,
        duration=6.0,
        shots=[s1, s2],
    )

    timeline = VisualTimeline(
        project_id="proj_1",
        total_duration_sec=6.0,
        target_resolution=TargetResolution(width=1920, height=1080),
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        scenes=[scene],
    )

    is_valid, warnings = validator.validate_timeline(timeline)
    assert is_valid is False
    assert any(w.warning_type == WarningType.VISUAL_TIMELINE_OVERLAP for w in warnings)


def test_validator_detects_missing_asset():
    validator = CompositionValidator()

    s1 = _make_dummy_shot("s1", 0.0, 3.0, asset_id="missing_asset_x")

    scene = MotionScene(
        scene_id="sc_1",
        scene_index=0,
        start_time=0.0,
        end_time=3.0,
        duration=3.0,
        shots=[s1],
    )

    timeline = VisualTimeline(
        project_id="proj_1",
        total_duration_sec=3.0,
        target_resolution=TargetResolution(width=1920, height=1080),
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        scenes=[scene],
    )

    is_valid, warnings = validator.validate_timeline(timeline, known_visual_asset_ids=["known_asset_1"])
    assert is_valid is False
    assert any(w.warning_type == WarningType.SOURCE_VISUAL_MISSING for w in warnings)
