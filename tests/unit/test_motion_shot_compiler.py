"""
Unit tests for compiling and composing motion graphic shots within PanelFlow RenderPlan.
"""

from pathlib import Path
import pytest
from PIL import Image

from engine.render.models.render_plan import RenderPlan, RenderShotPlan
from engine.render.models.profiles import RenderProfile
from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer


def test_compiler_emits_motion_graphic_shot(tmp_path):
    compiler = TimelineCompiler()
    story_state = {
        "scenes": [
            {
                "id": "scene_motion_1",
                "type": "motion_graphic",
                "motion_preset_id": "keynote_showcase",
                "duration_sec": 4.0,
                "motion_props": {
                    "headline": "NEXT GEN COMPILATION",
                    "subtitle": "Procedural Motion Engine",
                },
                "layers": [],
            }
        ]
    }
    profile = RenderProfile(width=1280, height=720, fps=30)
    plan = compiler.compile(
        state=story_state,
        project_id="test_proj",
        workspace_path=tmp_path,
        profile=profile,
    )

    assert len(plan.shots) == 1
    shot = plan.shots[0]
    assert shot.motion_graphic is not None
    assert shot.motion_graphic["preset_id"] == "keynote_showcase"
    assert shot.motion_graphic["props"]["headline"] == "NEXT GEN COMPILATION"
    assert shot.duration == 4.0


def test_composer_renders_motion_graphic_frame():
    profile = RenderProfile(width=1280, height=720, fps=30)
    shot = RenderShotPlan(
        shot_id="shot_mg_01",
        scene_id="scene_01",
        sequence_global=1,
        start_frame=0,
        end_frame=120,
        total_frames=120,
        start_time=0.0,
        end_time=4.0,
        duration=4.0,
        motion_graphic={
            "preset_id": "cyber_hud",
            "props": {
                "title": "QUANTUM CORE",
                "target_name": "UNIT_OMEGA",
            },
        },
    )
    plan = RenderPlan(
        project_id="test_proj",
        total_duration_sec=4.0,
        total_frames=120,
        profile=profile,
        shots=[shot],
        audio_tracks=[],
    )
    composer = FrameComposer()

    # Compose frame at t = 1.0s (frame 30)
    frame = composer.compose_frame(30, plan)
    assert frame.size == (1280, 720)
    assert frame.mode == "RGB"
