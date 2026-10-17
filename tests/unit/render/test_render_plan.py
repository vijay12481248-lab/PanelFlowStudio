"""
Unit tests for RenderPlan compilation, deterministic hashing, and preflight checking (Milestone 7).
"""
from pathlib import Path
from PIL import Image
import soundfile as sf
import numpy as np
import pytest

from engine.render.engine import RenderEngine
from engine.render.models.render_plan import RenderPlan, RenderShotPlan
from engine.render.models.profiles import RenderProfile
from engine.render.models.enums import ScalePolicy, MusicDurationPolicy
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval, TimelineSourceType


@pytest.fixture
def mock_visual_and_audio_project(tmp_path: Path):
    """Creates real files on disk for a 2-shot project."""
    # 1. Images
    img1 = tmp_path / "panel_01.jpg"
    img2 = tmp_path / "panel_02.jpg"
    Image.new("RGB", (1920, 1080), color=(100, 150, 200)).save(img1)
    Image.new("RGB", (1920, 1080), color=(200, 150, 100)).save(img2)

    # 2. Audio files
    audio1 = tmp_path / "speech_01.wav"
    audio2 = tmp_path / "speech_02.wav"
    bgm = tmp_path / "bgm.wav"

    t = np.linspace(0, 1.0, 48000, endpoint=False)
    sig = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(str(audio1), sig, 48000)
    sf.write(str(audio2), sig, 48000)
    sf.write(str(bgm), sig, 48000)

    # 3. MasterAudioTimeline
    mat = MasterAudioTimeline(
        project_id="proj_test",
        total_duration_sec=4.0,
        source_type=TimelineSourceType.REAL_AUDIO_TIMELINE,
        intervals=[
            AudioInterval(
                interval_id="int_01",
                script_segment_id="seg_01",
                speaker_character_id="char_alice",
                start_time=0.5,
                end_time=1.8,
                audio_file_uri=str(audio1),
                text="Hello world.",
                is_speech=True,
            ),
            AudioInterval(
                interval_id="int_02",
                script_segment_id="seg_02",
                speaker_character_id="char_bob",
                start_time=2.2,
                end_time=3.5,
                audio_file_uri=str(audio2),
                text="Response message.",
                is_speech=True,
            ),
        ],
    )

    # 4. VisualTimeline
    shot1 = Shot(
        shot_id="shot_1",
        scene_id="sc_1",
        sequence_global=1,
        source_asset_id="panel_1",
        source_panel_id="panel_1",
        start_time=0.0,
        end_time=2.0,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.1),
        motion_type=MotionType.SLOW_ZOOM_IN,
        easing=EasingFunction.EASE_IN_OUT,
    )
    shot2 = Shot(
        shot_id="shot_2",
        scene_id="sc_1",
        sequence_global=2,
        source_asset_id="panel_2",
        source_panel_id="panel_2",
        start_time=2.0,
        end_time=4.0,
        camera_start=CameraState(center_x=0.4, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.6, center_y=0.5, zoom=1.0),
        motion_type=MotionType.PAN_RIGHT,
        easing=EasingFunction.EASE_IN_OUT,
    )

    scene1 = MotionScene(
        scene_id="sc_1",
        sequence=1,
        title="Opening Scene",
        start_time=0.0,
        end_time=4.0,
        shots=[shot1, shot2],
    )

    vt = VisualTimeline(
        project_id="proj_test",
        total_duration_sec=4.0,
        total_shots=2,
        scenes=[scene1],
    )

    assets_map = {
        "panel_1": str(img1),
        "panel_2": str(img2),
    }

    return vt, mat, assets_map, str(bgm)


def test_compile_render_plan(mock_visual_and_audio_project):
    vt, mat, assets_map, bgm_path = mock_visual_and_audio_project
    engine = RenderEngine()

    plan = engine.compile_render_plan(
        timeline=vt,
        master_audio=mat,
        source_assets_map=assets_map,
        bgm_path=bgm_path,
        profile=RenderProfile.standard_1080p(),
        music_policy=MusicDurationPolicy.LOOP,
    )

    assert plan.total_duration_sec == 4.0
    assert plan.total_frames == 120  # 4.0s * 30 fps
    assert len(plan.shots) == 2

    # Shot 1 frames
    s1 = plan.shots[0]
    assert s1.start_frame == 0
    assert s1.end_frame == 60
    assert s1.total_frames == 60
    assert Path(s1.source_asset_path).name == "panel_01.jpg"

    # Shot 2 frames
    s2 = plan.shots[1]
    assert s2.start_frame == 60
    assert s2.end_frame == 120
    assert s2.total_frames == 60
    assert Path(s2.source_asset_path).name == "panel_02.jpg"

    # Audio tracks: 2 dialogue + 1 music = 3 tracks
    assert len(plan.audio_tracks) == 3
    dialogue_tracks = [t for t in plan.audio_tracks if t.track_type == "dialogue"]
    assert len(dialogue_tracks) == 2
    music_tracks = [t for t in plan.audio_tracks if t.track_type == "music"]
    assert len(music_tracks) == 1

    # Plan hash must be deterministic
    plan2 = engine.compile_render_plan(
        timeline=vt,
        master_audio=mat,
        source_assets_map=assets_map,
        bgm_path=bgm_path,
    )
    assert plan.hash == plan2.hash


def test_find_shot_at_frame(mock_visual_and_audio_project):
    vt, mat, assets_map, bgm_path = mock_visual_and_audio_project
    engine = RenderEngine()
    plan = engine.compile_render_plan(vt, mat, assets_map, bgm_path)

    # Frame 15 -> Shot 1
    shot_a = plan.find_shot_at_frame(15)
    assert shot_a is not None
    assert shot_a.shot_id == "shot_1"

    # Frame 60 -> Shot 2 (since shot 1 is [0, 60))
    shot_b = plan.find_shot_at_frame(60)
    assert shot_b is not None
    assert shot_b.shot_id == "shot_2"

    # Frame 150 -> None (out of bounds)
    assert plan.find_shot_at_frame(150) is None


def test_preflight_check(mock_visual_and_audio_project):
    vt, mat, assets_map, bgm_path = mock_visual_and_audio_project
    engine = RenderEngine()
    plan = engine.compile_render_plan(vt, mat, assets_map, bgm_path)

    # All files exist -> preflight passes
    passed, issues = engine.preflight_check(plan)
    assert passed is True
    assert len(issues) == 0

    # Corrupt a source asset path
    plan.shots[0].source_asset_path = "non_existent_file.png"
    passed_fail, issues_fail = engine.preflight_check(plan)
    assert passed_fail is False
    assert any("non_existent_file.png" in err for err in issues_fail)
