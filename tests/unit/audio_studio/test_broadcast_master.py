"""Tests for Broadcast Loudness Mastering: -14 LUFS YouTube, -23 LUFS EBU R128,
lookahead True-Peak limiting, and broadcast compliance verification.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest
import soundfile as sf
import numpy as np

from engine.audio.studio.master import (
    STANDARDS,
    check_compliance,
    get_standard_spec,
    master_audio,
    master_plan,
)
from engine.audio.studio.plan import Cue, PlanStore, SoundPlan, Track
from engine.audio.studio.sources.synth import SynthProvider
from engine.audio.studio.engine import AudioEngine

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make_tone_wav(path: Path, duration_s: float = 3.0, freq: float = 440.0, amp: float = 0.5) -> Path:
    sr = 48000
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Stereo tone
    left = amp * np.sin(2 * np.pi * freq * t)
    right = amp * np.sin(2 * np.pi * (freq * 1.5) * t)
    data = np.stack([left, right], axis=1).astype(np.float32)
    sf.write(str(path), data, sr, subtype="PCM_24")
    return path


def test_standard_specifications():
    yt = get_standard_spec("youtube")
    assert yt["target_lufs"] == -14.0
    assert yt["max_true_peak_db"] == -1.0
    assert yt["tolerance_lufs"] == 0.5

    ebu = get_standard_spec("ebu_r128")
    assert ebu["target_lufs"] == -23.0
    assert ebu["max_true_peak_db"] == -1.0

    custom = get_standard_spec("custom", custom_target_lufs=-16.0)
    assert custom["target_lufs"] == -16.0


def test_compliance_checker():
    # Compliant YouTube audio
    comp = check_compliance({"integrated_lufs": -14.2, "true_peak_db": -1.2, "lra": 8.0}, "youtube")
    assert comp["compliant"] is True
    assert len(comp["reasons"]) == 0

    # Non-compliant: too loud
    comp_loud = check_compliance({"integrated_lufs": -11.0, "true_peak_db": -0.5, "lra": 8.0}, "youtube")
    assert comp_loud["compliant"] is False
    assert any("outside target" in r for r in comp_loud["reasons"])
    assert any("exceeds maximum ceiling" in r for r in comp_loud["reasons"])

    # Non-compliant: silent
    comp_silent = check_compliance({"integrated_lufs": -120.0, "true_peak_db": -120.0, "lra": 0.0}, "youtube")
    assert comp_silent["compliant"] is False
    assert any("silent" in r for r in comp_silent["reasons"])


def test_master_audio_youtube(tmp_path):
    input_wav = _make_tone_wav(tmp_path / "input.wav", duration_s=4.0, amp=0.7)
    out_wav = tmp_path / "master_yt.wav"

    res = master_audio(input_wav, out_wav, standard="youtube")
    assert out_wav.is_file()
    assert res["standard"] == "youtube"
    assert res["target_lufs"] == -14.0

    loudness = res["loudness"]
    assert abs(loudness["integrated_lufs"] - (-14.0)) <= 0.6
    assert loudness["true_peak_db"] <= -0.9  # lookahead limiter caps peak at -1.0 dBTP
    assert res["compliance"]["compliant"] is True


def test_master_audio_ebu_r128(tmp_path):
    input_wav = _make_tone_wav(tmp_path / "input.wav", duration_s=4.0, amp=0.7)
    out_wav = tmp_path / "master_ebu.wav"

    res = master_audio(input_wav, out_wav, standard="ebu_r128")
    assert out_wav.is_file()
    assert res["standard"] == "ebu_r128"
    assert res["target_lufs"] == -23.0

    loudness = res["loudness"]
    assert abs(loudness["integrated_lufs"] - (-23.0)) <= 0.6
    assert loudness["true_peak_db"] <= -0.9
    assert res["compliance"]["compliant"] is True


def test_master_plan_integration(tmp_path):
    store = PlanStore(tmp_path / "store")
    engine = AudioEngine(store, [SynthProvider()])

    # Create dummy video
    video_p = tmp_path / "video.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3:r=24",
           "-f", "lavfi", "-i", "sine=frequency=400:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", str(video_p)]
    subprocess.run(cmd, check=True)

    plan = engine.create_plan(video_p)
    plan.cues.append(Cue(id="c1", track="sfx", kind="impact", intent="hit", hit_t=1.0))
    engine.store.save(plan)

    plan = engine.source_cue(plan.id, "c1", mode="auto")
    out_master = tmp_path / "plan_master.wav"
    out_video = tmp_path / "plan_master.mp4"

    res = master_plan(
        plan,
        out_master,
        standard="youtube",
        video_in=video_p,
        out_video=out_video,
    )

    assert out_master.is_file()
    assert out_video.is_file()
    assert res["standard"] == "youtube"
    assert res["compliance"]["compliant"] is True
