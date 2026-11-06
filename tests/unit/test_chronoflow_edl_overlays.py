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


def _dur(path):
    return pl.ChronoFlowPipeline._probe_size_and_duration(path)[2]


@pytest.fixture()
def trio(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(pl, "STUDIO_OUTPUT_DIR", out)
    monkeypatch.setattr(pl, "COMFY_INPUT_DIR", tmp_path / "in")
    monkeypatch.setattr(pl, "COMFY_OUTPUT_DIR", tmp_path / "none")
    for name, color in (("a", "blue"), ("b", "red"), ("c", "blue")):
        _clip(out / f"{name}.mp4", color)
    return out, tmp_path


def _edl(*spec):
    return [{"filename": f"{n}.mp4", "in_point": 0, "out_point": 2, "transition": t, "trans_dur": 0.5} for n, t in spec]


def test_dissolve_overlaps_clips_and_blends_the_middle(trio):
    out, tmp = trio
    master = out / "m.mp4"
    assert pl.ChronoFlowPipeline().render_timeline_edl(_edl(("a", "cut"), ("b", "dissolve")), master)
    assert _dur(master) == pytest.approx(3.5, abs=0.1)            # 2 + 2 - 0.5 overlap, exactly what the timeline shows
    _, early = _pixel_at(master, 0.8, tmp)
    _, mid = _pixel_at(master, 1.75, tmp)
    _, late = _pixel_at(master, 3.0, tmp)
    assert early[2] > 150 and early[0] < 60                       # still blue
    assert mid[0] > 60 and mid[2] > 60                            # both colours present: a real crossfade
    assert late[0] > 150 and late[2] < 60                         # red


def test_dip_to_black_goes_dark_mid_transition_and_a_cut_after_it_stays_exact(trio):
    out, tmp = trio
    master = out / "m.mp4"
    assert pl.ChronoFlowPipeline().render_timeline_edl(_edl(("a", "cut"), ("b", "fadeblack"), ("c", "cut")), master)
    assert _dur(master) == pytest.approx(5.5, abs=0.1)            # 6 s of clips minus one 0.5 s overlap; the cut adds no loss
    _, mid = _pixel_at(master, 1.75, tmp)
    assert max(mid) < 40                                          # black at the midpoint (the editor previews a symmetric dip)
    _, quarter = _pixel_at(master, 1.625, tmp)
    _, three_q = _pixel_at(master, 1.875, tmp)
    assert max(quarter) > max(mid) and max(three_q) > max(mid)    # brighter on both sides of the dip, not just one
    _, last = _pixel_at(master, 4.5, tmp)
    assert last[2] > 150 and last[0] < 60                         # clip c after the hard cut
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(master)], capture_output=True, text=True).stdout
    assert "audio" in streams
