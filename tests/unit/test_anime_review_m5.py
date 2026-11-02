import subprocess
import wave

import numpy as np
import pytest

from engine.anime.review import packaging, render
from engine.anime.review.models import ReviewScript, ScriptSegment, Timeline, TimelineEntry


def test_caption_chunks_cover_speech_exactly():
    ch = render.caption_chunks(" ".join(["w"] * 20), 6.0)
    assert len(ch) == 3 and ch[0][0] == 0 and ch[-1][1] == pytest.approx(6.0)
    assert all(len(t.split()) <= render.MAX_CAPTION_WORDS for _, _, t in ch)


def test_srt_format():
    assert render.srt_text([(1.5, 2.25, "hi")], offset=10).startswith("1\n00:00:11,500 --> 00:00:12,250\nhi")


def _tl(starts):
    roles = ["hook", "recap", "highlight", "critique", "verdict", "cta"][:len(starts)]
    segs = [ScriptSegment(id=f"s{i}", clip_id="c", role=r, text="t") for i, r in enumerate(roles)]
    es = [TimelineEntry(segment_id=s.id, clip_id="c", audio_path="x", audio_sec=1, timeline_start=t, src_start=0, src_len=1)
          for s, t in zip(segs, starts)]
    return ReviewScript(title_hook="h", rating=7, segments=segs), Timeline(fps=30, total_sec=100, entries=es, voice="v")


def test_chapters_valid_for_youtube():
    sc, tl = _tl([0, 12, 30, 45, 60, 75])
    ch = packaging.chapters(sc, tl)
    assert ch[0][0] == "0:00" and len(ch) >= 3 and ch[-1][1] == "Verdict" and [l for _, l in ch].count("Verdict") == 1


def test_chapters_dropped_when_too_few():
    sc, tl = _tl([0, 3, 6, 9])
    assert packaging.chapters(sc, tl) == []


def test_render_segment_is_exact_length(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=24:d=4", "-f", "lavfi",
                    "-i", "sine=d=4", "-shortest", "-pix_fmt", "yuv420p", str(src)], check=True)
    wav = tmp_path / "v.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(np.zeros(24000 * 3).astype("<i2").tobytes())  # 3.0 s
    e = TimelineEntry(segment_id="s1", clip_id="c", audio_path=str(wav), audio_sec=3.0, timeline_start=0,
                      src_start=0, src_len=2.0, speed=0.8, hold_sec=0.5)
    out = tmp_path / "o.mp4"
    render.render_segment(e, "hello there friend", src, True, 30.0, tmp_path, True, out)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames,width,height", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert n.split(",") == ["1920", "1080", "90"]


def test_long_hold_zooms_slowly_and_keeps_exact_length(tmp_path):
    from PIL import Image, ImageChops

    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=640x360:r=24:d=4", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    wav = tmp_path / "v.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(np.zeros(24000 * 3).astype("<i2").tobytes())
    e = TimelineEntry(segment_id="s1", clip_id="c", audio_path=str(wav), audio_sec=3.0, timeline_start=0,
                      src_start=0, src_len=1.0, speed=1.0, hold_sec=2.0)
    out = tmp_path / "o.mp4"
    render.render_segment(e, "hold test", src, False, 30.0, tmp_path, False, out)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert n == "90"
    for t, name in ((1.2, "a.png"), (2.9, "b.png")):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", str(tmp_path / name)], check=True)
    diff = ImageChops.difference(Image.open(tmp_path / "a.png").convert("RGB"), Image.open(tmp_path / "b.png").convert("RGB"))
    assert diff.getbbox() is not None  # the held frame is slowly zooming, not frozen
