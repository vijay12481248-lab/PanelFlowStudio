"""
End-to-End Integration Test for PanelFlow Production Renderer (Milestone 7).
Verifies complete render cycle using synthetic assets:
RenderPlan -> Audio Mixdown -> FFmpeg Pipe -> MP4 -> ffprobe Stream Audit -> Contact Sheet.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import pytest
import soundfile as sf

from engine.render.engine import RenderEngine
from engine.render.models.profiles import RenderProfile
from engine.render.models.enums import (
    RenderStage,
    ScalePolicy,
    MusicDurationPolicy,
)
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction, TimelineSourceType
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval
from engine.motion.models.cues import CaptionCue


@pytest.fixture
def synthetic_render_project(tmp_path: Path):
    """Generates synthetic panels and audio for a 3-second render test."""
    # 1. Source visual assets (1920x1080)
    p1 = tmp_path / "panel_01.png"
    p2 = tmp_path / "panel_02.png"

    img1 = Image.new("RGB", (1920, 1080), color=(50, 70, 120))
    draw1 = ImageDraw.Draw(img1)
    draw1.text((200, 200), "PANEL 01 SYNTHETIC", fill=(255, 255, 255))
    draw1.rectangle([300, 300, 800, 800], fill=(220, 100, 100))
    img1.save(p1)

    img2 = Image.new("RGB", (1920, 1080), color=(120, 70, 50))
    draw2 = ImageDraw.Draw(img2)
    draw2.text((200, 200), "PANEL 02 SYNTHETIC", fill=(255, 255, 255))
    draw2.rectangle([1000, 300, 1500, 800], fill=(100, 220, 100))
    img2.save(p2)

    # 2. Audio assets
    speech1_path = tmp_path / "speech_01.wav"
    speech2_path = tmp_path / "speech_02.wav"
    music_path = tmp_path / "music.wav"

    sr = 48000
    # Speech 1: 1.0s tone
    t1 = np.linspace(0, 1.0, sr, endpoint=False)
    s1 = (0.4 * np.sin(2 * np.pi * 500 * t1)).astype(np.float32)
    sf.write(str(speech1_path), s1, sr)

    # Speech 2: 0.8s tone
    t2 = np.linspace(0, 0.8, int(sr * 0.8), endpoint=False)
    s2 = (0.4 * np.sin(2 * np.pi * 650 * t2)).astype(np.float32)
    sf.write(str(speech2_path), s2, sr)

    # Music: 2.0s loop
    tm = np.linspace(0, 2.0, sr * 2, endpoint=False)
    m = (0.15 * np.sin(2 * np.pi * 220 * tm)).astype(np.float32)
    sf.write(str(music_path), m, sr)

    # 3. MasterAudioTimeline (3.0 seconds total)
    mat = MasterAudioTimeline(
        project_id="synth_proj",
        total_duration_sec=3.0,
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        intervals=[
            AudioInterval(
                interval_id="iv_01",
                script_segment_id="seg_01",
                start_time=0.2,
                end_time=1.2,
                audio_file_uri=str(speech1_path),
                text="First synthetic dialogue line.",
                is_speech=True,
            ),
            AudioInterval(
                interval_id="iv_02",
                script_segment_id="seg_02",
                start_time=1.6,
                end_time=2.4,
                audio_file_uri=str(speech2_path),
                text="Second synthetic dialogue line.",
                is_speech=True,
            ),
        ],
    )

    # 4. VisualTimeline (2 shots: 1.5s each)
    shot1 = Shot(
        shot_id="shot_01",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_id="p1",
        start_time=0.0,
        end_time=1.5,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.15),
        motion_type=MotionType.SLOW_ZOOM_IN,
        easing=EasingFunction.EASE_IN_OUT,
        caption_cues=[
            CaptionCue(
                cue_id="cap_1",
                shot_id="shot_01",
                text="First synthetic dialogue line.",
                start_time=0.2,
                end_time=1.2,
            )
        ],
    )

    shot2 = Shot(
        shot_id="shot_02",
        scene_id="sc_01",
        sequence_global=2,
        source_asset_id="p2",
        start_time=1.5,
        end_time=3.0,
        camera_start=CameraState(center_x=0.4, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.6, center_y=0.5, zoom=1.0),
        motion_type=MotionType.PAN_RIGHT,
        easing=EasingFunction.EASE_IN_OUT,
        caption_cues=[
            CaptionCue(
                cue_id="cap_2",
                shot_id="shot_02",
                text="Second synthetic dialogue line.",
                start_time=1.6,
                end_time=2.4,
            )
        ],
    )

    scene = MotionScene(
        scene_id="sc_01",
        sequence=1,
        title="Synthetic Scene",
        start_time=0.0,
        end_time=3.0,
        shots=[shot1, shot2],
    )

    vt = VisualTimeline(
        project_id="synth_proj",
        total_duration_sec=3.0,
        total_shots=2,
        scenes=[scene],
    )

    assets_map = {"p1": str(p1), "p2": str(p2)}

    return vt, mat, assets_map, str(music_path)


def test_render_e2e_synthetic_mp4(synthetic_render_project, tmp_path: Path):
    vt, mat, assets_map, music_path = synthetic_render_project
    engine = RenderEngine()

    # Verify FFmpeg is available on host
    runtime = engine.encoder.check_runtime()
    if not runtime["available"]:
        pytest.skip(f"FFmpeg not installed or available: {runtime.get('error')}")

    out_mp4 = tmp_path / "output_test_render.mp4"
    workspace = tmp_path / "render_work"

    # Track progress stages reported by callback
    stages_seen = []

    def progress_callback(stage: RenderStage, current: int, total: int, pct: float):
        stages_seen.append(stage)

    # 1. Compile RenderPlan
    plan = engine.compile_render_plan(
        timeline=vt,
        master_audio=mat,
        source_assets_map=assets_map,
        bgm_path=music_path,
        profile=RenderProfile.standard_1080p(),
        music_policy=MusicDurationPolicy.LOOP,
    )

    assert plan.total_frames == 90  # 3.0s * 30 fps
    assert len(plan.shots) == 2
    assert len(plan.audio_tracks) == 3

    # 2. Execute Render
    audit_report = engine.execute_render(
        plan=plan,
        output_mp4_path=out_mp4,
        workspace_dir=workspace,
        progress_cb=progress_callback,
    )

    # 3. Verify Output
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 50000  # Valid MP4 with frames and audio

    # Verify progress stages
    assert RenderStage.PREPARING in stages_seen
    assert RenderStage.ENCODING in stages_seen
    assert RenderStage.VALIDATING in stages_seen
    assert RenderStage.COMPLETE in stages_seen

    # 4. Verify Post-Render Audit
    assert audit_report.is_valid is True
    assert audit_report.file_size_bytes > 0
    assert pytest.approx(audit_report.actual_duration_sec, abs=0.4) == 3.0
    assert audit_report.ffprobe_meta.get("width") == 1920
    assert audit_report.ffprobe_meta.get("height") == 1080
    assert "h264" in audit_report.ffprobe_meta.get("video_codec", "").lower()
    assert "aac" in audit_report.ffprobe_meta.get("audio_codec", "").lower()

    # 5. Verify Frame Samples and Contact Sheet
    assert len(audit_report.frame_samples) >= 4
    assert audit_report.quality_flags["black_frames"] == 0
    assert audit_report.contact_sheet_path is not None
    assert Path(audit_report.contact_sheet_path).exists()
