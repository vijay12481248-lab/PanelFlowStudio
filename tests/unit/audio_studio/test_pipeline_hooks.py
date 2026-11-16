"""Tests for Studio Pipeline Automation Hooks: Story Studio and Anime Review.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.pipeline_hooks import (
    auto_soundtrack_anime_review,
    auto_soundtrack_original_story,
)
from engine.audio.studio.plan import PlanStore
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def test_video(tmp_path):
    p = tmp_path / "scene_cut.mp4"
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:d=2:r=24",
        "-f", "lavfi", "-i", "color=c=white:s=160x120:d=2:r=24",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)
    ]
    subprocess.run(cmd, check=True)
    return p


@pytest.fixture
def test_narration(tmp_path):
    p = tmp_path / "narration.wav"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=3", "-ar", "48000", "-ac", "1", str(p)]
    subprocess.run(cmd, check=True)
    return p


def test_auto_soundtrack_original_story(test_video, test_narration, tmp_path):
    store = PlanStore(tmp_path / "store")
    engine = AudioEngine(store, [SynthProvider()])

    res = auto_soundtrack_original_story(
        engine,
        video_path=test_video,
        narration_path=test_narration,
        story_title="Epic Battle",
        use_vision=False,
        standard="youtube",
    )

    assert "plan_id" in res
    assert res["cues_total"] >= 1  # Cut spotted
    assert Path(res["master_wav"]).is_file()
    assert Path(res["master_video"]).is_file()
    assert res["compliance"]["compliant"] is True


def test_auto_soundtrack_anime_review(test_video, test_narration, tmp_path):
    store = PlanStore(tmp_path / "store")
    engine = AudioEngine(store, [SynthProvider()])

    res = auto_soundtrack_anime_review(
        engine,
        video_path=test_video,
        narration_path=test_narration,
        standard="youtube",
    )

    assert "plan_id" in res
    assert Path(res["master_wav"]).is_file()
    assert Path(res["master_video"]).is_file()
    assert res["compliance"]["compliant"] is True
