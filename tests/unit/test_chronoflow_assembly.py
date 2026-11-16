"""Unit tests for ChronoFlow Storyboard Sequence Assembly & Downstream Invalidation."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.chronoflow import start_modes
from engine.chronoflow.media_tools import _FFMPEG, probe
from engine.chronoflow.timeline_assemble import (
    assemble_storyboard_sequence,
    resolve_scene_clip,
)
from engine.mcp.registry import registry
import engine.mcp.tools


@pytest.fixture
def client():
    return TestClient(app)


def _generate_synthetic_clip(path: Path, width: int, height: int, duration_s: float = 1.0, fps: int = 24) -> Path:
    """Generate a valid test H.264 video using ffmpeg testsrc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _FFMPEG, "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_s}:size={width}x{height}:rate={fps}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg synthetic clip generation failed: {res.stderr}"
    assert path.is_file()
    return path


def test_invalidate_downstream_linear_chain():
    scenes = [
        {"shot_index": 1, "inherits_tail": False, "approved": True, "state": "approved", "prev_tail": ""},
        {"shot_index": 2, "inherits_tail": True, "first_frame": "", "approved": True, "state": "approved", "prev_tail": "tail_1.png"},
        {"shot_index": 3, "inherits_tail": True, "first_frame": "", "approved": True, "state": "approved", "prev_tail": "tail_2.png"},
    ]
    invalidated = start_modes.invalidate_downstream(scenes, 0)
    assert invalidated == [1, 2]
    assert scenes[1]["state"] == "stale"
    assert scenes[1]["approved"] is False
    assert scenes[1]["prev_tail"] == ""
    assert scenes[2]["state"] == "stale"
    assert scenes[2]["approved"] is False
    assert scenes[2]["prev_tail"] == ""


def test_invalidate_downstream_broken_by_explicit_first_frame():
    scenes = [
        {"shot_index": 1, "inherits_tail": False, "approved": True, "state": "approved"},
        {"shot_index": 2, "inherits_tail": True, "first_frame": "custom_frame.png", "approved": True, "state": "approved"},
        {"shot_index": 3, "inherits_tail": True, "first_frame": "", "approved": True, "state": "approved"},
    ]
    invalidated = start_modes.invalidate_downstream(scenes, 0)
    # Card 2 has an explicit first frame, breaking the dependency chain
    assert invalidated == []
    assert scenes[1]["approved"] is True
    assert scenes[2]["approved"] is True


def test_invalidate_downstream_middle_card_redo():
    scenes = [
        {"shot_index": 1, "inherits_tail": False, "approved": True, "state": "approved"},
        {"shot_index": 2, "inherits_tail": True, "first_frame": "", "approved": True, "state": "approved"},
        {"shot_index": 3, "inherits_tail": True, "first_frame": "", "approved": True, "state": "approved"},
    ]
    invalidated = start_modes.invalidate_downstream(scenes, 1)
    # Only card 3 is downstream of card 2
    assert invalidated == [2]
    assert scenes[0]["approved"] is True
    assert scenes[1]["approved"] is True
    assert scenes[2]["approved"] is False
    assert scenes[2]["state"] == "stale"


def test_check_assembly_readiness():
    # Empty scenes
    ok, probs = start_modes.check_assembly_readiness([])
    assert ok is False
    assert "no shots" in probs[0].lower()

    # Unrendered shots
    scenes = [
        {"shot_index": 1, "rendered_video_filename": "shot_1.mp4", "state": "approved"},
        {"shot_index": 2, "state": "ready"},
    ]
    ok, probs = start_modes.check_assembly_readiness(scenes)
    assert ok is False
    assert "Shot 2 has not been rendered" in probs[0]

    # Stale video
    scenes_stale = [
        {"shot_index": 1, "rendered_video_filename": "shot_1.mp4", "state": "ready"},
        {"shot_index": 2, "rendered_video_filename": "shot_2.mp4", "state": "stale"},
    ]
    ok, probs = start_modes.check_assembly_readiness(scenes_stale)
    assert ok is False
    assert "Shot 2 has stale video" in probs[0]

    # Approved only
    scenes_mix = [
        {"shot_index": 1, "rendered_video_filename": "shot_1.mp4", "approved": True},
        {"shot_index": 2, "state": "empty", "approved": False},
    ]
    ok, probs = start_modes.check_assembly_readiness(scenes_mix, approved_only=True)
    assert ok is True
    assert probs == []


def test_resolve_scene_clip(tmp_path):
    test_file = tmp_path / "test_shot_clip.mp4"
    test_file.write_bytes(b"dummy")

    scene_abs = {"video_file": str(test_file)}
    assert resolve_scene_clip(scene_abs, [tmp_path]) == test_file.resolve()

    scene_name = {"rendered_video_filename": "test_shot_clip.mp4"}
    assert resolve_scene_clip(scene_name, [tmp_path]) == test_file.resolve()

    scene_url = {"video_url": "/chronoflow/outputs/test_shot_clip.mp4"}
    assert resolve_scene_clip(scene_url, [tmp_path]) == test_file.resolve()

    scene_missing = {"rendered_video_filename": "non_existent.mp4"}
    assert resolve_scene_clip(scene_missing, [tmp_path]) is None


def test_assemble_storyboard_sequence_synthetic_ffmpeg(tmp_path):
    """Test actual video concatenation and mixed-resolution normalization with FFmpeg."""
    clip1 = _generate_synthetic_clip(tmp_path / "shot_1_960x544.mp4", 960, 544, duration_s=1.0)
    clip2 = _generate_synthetic_clip(tmp_path / "shot_2_1344x768.mp4", 1344, 768, duration_s=1.0)

    scenes = [
        {
            "shot_index": 1,
            "title": "Opening Scene",
            "rendered_video_filename": clip1.name,
            "duration": 1.0,
            "narration": "The journey begins in the forgotten valley.",
            "prompt": "Cinematic shot of ancient ruins with morning mist.",
        },
        {
            "shot_index": 2,
            "title": "Action Arrival",
            "rendered_video_filename": clip2.name,
            "duration": 1.0,
            "narration": "A shadowy figure approaches swiftly.",
            "prompt": "Fast tracking push-in of a warrior drawing their blade.",
        },
    ]

    master_out = tmp_path / "assembled_master.mp4"
    result = assemble_storyboard_sequence(
        scenes=scenes,
        out_path=master_out,
        target_width=1920,
        target_height=1080,
        fps=24.0,
        search_dirs=[tmp_path],
        create_sound_plan=True,
        sound_plan_title="Synthetic Assembly Sound Plan",
    )

    assert result["success"] is True
    assert master_out.is_file()
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["fps"] == 24.0
    assert result["shot_count"] == 2

    info = probe(master_out)
    assert info["width"] == 1920
    assert info["height"] == 1080
    assert info["has_audio"] is True
    assert 1.8 <= info["duration"] <= 2.2

    # Verify Audio Studio Sound Plan integration
    assert result["sound_plan_id"] is not None
    from engine.api.routers.audio_studio import get_engine
    audio_engine = get_engine()
    plan = audio_engine.store.load(result["sound_plan_id"])
    assert plan is not None
    assert plan.note == "Synthetic Assembly Sound Plan"
    assert len(plan.cuts) >= 2
    # Plan should have dialogue cues for both shots
    dialogue_cues = [c for c in plan.cues if c.track == "dialogue"]
    assert len(dialogue_cues) == 2
    assert "journey begins" in dialogue_cues[0].intent
    assert "shadowy figure" in dialogue_cues[1].intent

    # Plan should have foley cues for both shots
    foley_cues = [c for c in plan.cues if c.track == "foley"]
    assert len(foley_cues) == 2


def test_assemble_storyboard_missing_clip_raises_400(tmp_path):
    scenes = [
        {"shot_index": 1, "title": "Shot 1", "rendered_video_filename": "missing_video.mp4"}
    ]
    out_path = tmp_path / "out.mp4"
    with pytest.raises(HTTPException) as excinfo:
        assemble_storyboard_sequence(scenes, out_path, search_dirs=[tmp_path])
    assert excinfo.value.status_code == 400
    assert "Shot 1" in excinfo.value.detail


def test_chronoflow_storyboard_assemble_api_endpoint(client, tmp_path, monkeypatch):
    """Test API endpoint POST /api/chronoflow/storyboard/assemble."""
    from engine.chronoflow.pipeline import STUDIO_OUTPUT_DIR
    clip1 = _generate_synthetic_clip(STUDIO_OUTPUT_DIR / "api_test_clip1.mp4", 960, 544, duration_s=1.0)
    clip2 = _generate_synthetic_clip(STUDIO_OUTPUT_DIR / "api_test_clip2.mp4", 1344, 768, duration_s=1.0)

    try:
        payload = {
            "scenes": [
                {"shot_index": 1, "rendered_video_filename": clip1.name, "duration": 1.0, "narration": "Narration 1"},
                {"shot_index": 2, "rendered_video_filename": clip2.name, "duration": 1.0, "prompt": "Action 2"},
            ],
            "title": "API Test Sequence",
            "target_width": 1920,
            "target_height": 1080,
            "fps": 24.0,
            "create_sound_plan": True,
        }

        resp = client.post("/api/chronoflow/storyboard/assemble", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["shot_count"] == 2
        assert data["sound_plan_id"] is not None

        # Test check readiness endpoint
        resp_check = client.post("/api/chronoflow/storyboard/check_readiness", json={"scenes": payload["scenes"]})
        assert resp_check.status_code == 200
        assert resp_check.json()["is_ready"] is True

        # Test invalidate downstream endpoint
        resp_inval = client.post("/api/chronoflow/storyboard/invalidate_downstream", json={
            "scenes": [
                {"shot_index": 1, "inherits_tail": False, "approved": True},
                {"shot_index": 2, "inherits_tail": True, "approved": True},
            ],
            "modified_index": 0
        })
        assert resp_inval.status_code == 200
        assert resp_inval.json()["invalidated_indices"] == [1]

    finally:
        # Cleanup synthetic test clips
        clip1.unlink(missing_ok=True)
        clip2.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_mcp_assemble_storyboard_tool():
    """Verify registration and schema of panelflow_chronoflow_assemble_storyboard MCP tool."""
    tool = registry.get_tool("panelflow_chronoflow_assemble_storyboard")
    assert tool is not None
    assert "scenes" in tool.input_schema["properties"]
    assert "create_sound_plan" in tool.input_schema["properties"]
