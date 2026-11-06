"""The baked master must contain V2 overlay frames only inside their window, at the clips' native size."""

import shutil
import subprocess

import pytest
from PIL import Image

from engine.chronoflow import pipeline as pl

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _clip(path, color):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:size=320x240:rate=24:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True)


def _pixel_at(video, t, tmp):
    png = tmp / f"f_{t}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(png)], check=True)
    im = Image.open(png).convert("RGB")
    return im.size, im.getpixel((im.width // 2, im.height // 2))


def test_overlay_is_burned_only_inside_its_window_at_native_size(tmp_path, monkeypatch):
    out, inp = tmp_path / "out", tmp_path / "in"
    out.mkdir(); inp.mkdir()
    monkeypatch.setattr(pl, "STUDIO_OUTPUT_DIR", out)
    monkeypatch.setattr(pl, "COMFY_INPUT_DIR", inp)
    monkeypatch.setattr(pl, "COMFY_OUTPUT_DIR", tmp_path / "none")
    _clip(out / "a.mp4", "blue")
    _clip(out / "b.mp4", "blue")
    Image.new("RGB", (320, 240), (255, 0, 0)).save(inp / "fix.png")

    master = out / "master.mp4"
    clips = [{"filename": "a.mp4", "in_point": 0, "out_point": 2}, {"filename": "b.mp4", "in_point": 0, "out_point": 2}]
    overlays = [{"filename": "fix.png", "start": 1.0, "duration": 1.0},
                {"filename": "../escape.png", "start": 0, "duration": 4}]          # path traversal must be ignored
    assert pl.ChronoFlowPipeline().render_timeline_edl(clips, master, overlays)

    size, inside = _pixel_at(master, 1.5, tmp_path)
    _, before = _pixel_at(master, 0.5, tmp_path)
    _, after = _pixel_at(master, 2.5, tmp_path)
    assert size == (320, 240)                                   # native size, not letterboxed to 1344x768
    assert inside[0] > 200 and inside[2] < 80                   # red overlay
    assert before[2] > 150 and before[0] < 80                   # still the blue clip
    assert after[2] > 150 and after[0] < 80
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(master)], capture_output=True, text=True).stdout
    assert "audio" in probe                                     # voice track survives the overlay pass


def test_mux_source_audio_carries_original_narration_onto_a_silent_variant(tmp_path):
    src, var = tmp_path / "orig.mp4", tmp_path / "variant.mp4"
    _clip(src, "blue")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=green:size=320x240:rate=24:duration=1.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(var)], check=True)       # video only, like a fresh render
    assert pl.ChronoFlowPipeline().mux_source_audio(var, src, offset_sec=0.5)
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(var)], capture_output=True, text=True).stdout
    assert "audio" in streams and "video" in streams
    _, _, dur = pl.ChronoFlowPipeline._probe_size_and_duration(var)
    assert dur == pytest.approx(1.5, abs=0.15)                                             # video length is preserved
