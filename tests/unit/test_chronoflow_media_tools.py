"""Timeline media helpers run against a real ffmpeg-generated clip (video + 440 Hz tone + a silent clip)."""

import shutil
import subprocess

import pytest
from PIL import Image

from engine.chronoflow import media_tools

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make(path, audio: bool):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture()
def media(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(media_tools, "STUDIO_OUTPUT_DIR", out)
    monkeypatch.setattr(media_tools, "COMFY_INPUT_DIR", tmp_path / "in")
    monkeypatch.setattr(media_tools, "CACHE_DIR", out / ".nle_cache")
    _make(out / "tone.mp4", audio=True)
    _make(out / "silent.mp4", audio=False)
    return out


def test_resolve_media_accepts_bare_names_only(media):
    assert media_tools.resolve_media("tone.mp4") == media / "tone.mp4"
    for bad in ("../tone.mp4", "sub/tone.mp4", "..\\tone.mp4", ".nle_cache", "missing.mp4", ""):
        assert media_tools.resolve_media(bad) is None


def test_probe_reports_real_stream_facts(media):
    info = media_tools.probe(media / "tone.mp4")
    assert (info["width"], info["height"], info["fps"]) == (320, 240, 24.0)
    assert info["duration"] == pytest.approx(2.0, abs=0.1)
    assert info["has_audio"] is True
    assert media_tools.probe(media / "silent.mp4")["has_audio"] is False


def test_filmstrip_is_one_sprite_of_n_frames_and_cached(media):
    sprite = media_tools.filmstrip(media / "tone.mp4", count=8, height=60)
    width, height = Image.open(sprite).size
    assert height == 60 and width == 8 * 80  # 4:3 tiles
    assert media_tools.filmstrip(media / "tone.mp4", count=8, height=60) == sprite


def test_waveform_peaks_follow_the_audio(media):
    peaks = media_tools.waveform(media / "tone.mp4", bins=50)
    assert len(peaks) == 50 and 0.11 < max(peaks) < 0.15  # ffmpeg's default sine is 1/8 full scale
    assert media_tools.waveform(media / "silent.mp4", bins=50) == []
