import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from engine.narration.runtime import audio as rt
from engine.original import video as v
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene


class FakeTts:
    def __init__(self):
        self.calls = []

    def synth(self, text, voice, rate):
        self.calls.append((text, voice))
        return (0.3 * np.sin(np.linspace(0, 300, int(rt.SR * 0.15 * len(text.split()))))).astype(np.float32)


def story(genre="bedtime"):
    chars = [Character(id=i, name=n, role=r, age_group="child", look="a, b, c, d", personality="p")
             for i, n, r in (("mira", "Mira", "protagonist"), ("pip", "Pip", "other"))]
    b = Bible(premise=Premise(title="Mira and the Moon", genre=genre, logline="A girl helps the moon.", tone="t", setting="s"),
              characters=chars, locations=[Location(id="attic", name="Attic", look="a, b, c, d")])
    texts = ["Mira looks out of the window at the quiet night sky.", "The moon smiles down at her and Pip the owl.",
             "Pip hoots softly and they both settle down to sleep."]
    panels = [Panel(id=f"p{i + 1:03d}", scene_id=f"sc{i // 2 + 1:02d}", shot="wide", angle="eye_level", location_id="attic",
                    character_ids=["mira"], action="Mira at the window", caption=t,
                    dialogue=[Line(speaker_id="pip", text="Hoo hoo")] if i == 1 else []) for i, t in enumerate(texts)]
    scenes = [Scene(id="sc01", location_id="attic", character_ids=["mira"], summary="Mira watches the moon. More.", mood="m"),
              Scene(id="sc02", location_id="attic", character_ids=["mira"], summary="Mira falls asleep.", mood="m")]
    return OriginalStory(bible=b, scenes=scenes, panels=panels)


def make_images(ws, n=3):
    (ws / "panels").mkdir(parents=True)
    for i in range(n):
        Image.new("RGB", (1344, 768), (40 * i + 30, 80, 120)).save(ws / "panels" / f"p{i + 1:03d}.png")


def test_voices_narrator_per_genre_and_distinct_character_voices():
    nar, chars = v.voices_for(story("horror"))
    assert nar[0] == "bm_george" and len({x[0] for x in chars.values()}) == 2 and nar[0] not in {x[0] for x in chars.values()}


def test_voice_panel_is_frame_aligned_min_length_and_reads_caption_then_dialogue(tmp_path):
    s, tts = story(), FakeTts()
    nar, chars = v.voices_for(s)
    d = v.voice_panel(tts, s.panels[1], nar, chars, 30.0, tmp_path / "a.wav")
    assert [c[1] for c in tts.calls] == [nar[0], chars["pip"][0]]  # storyteller first, then Pip in his own voice
    assert d * 30 == pytest.approx(round(d * 30), abs=1e-3) and d >= v.MIN_PANEL_SEC


def _marked_picture(path, w, h):
    """64px colour blocks (compress cleanly, but any shift or zoom changes many pixels) with a 24px RED band along the top and a
    24px BLUE band along the bottom (so any crop shows)."""
    cells = np.random.default_rng(1).integers(60, 200, (h // 64 + 1, w // 64 + 1, 3), dtype=np.uint8)
    a = np.kron(cells, np.ones((64, 64, 1), dtype=np.uint8))[:h, :w].copy()
    a[:24], a[-24:] = (255, 0, 0), (0, 0, 255)
    Image.fromarray(a).save(path)


def _frame_at(video, seconds, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(seconds), "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return np.asarray(Image.open(out).convert("RGB")).astype(int)


def _render_still(tmp_path, name, w, h):
    (tmp_path / "panels").mkdir(exist_ok=True)
    img = tmp_path / "panels" / f"{name}.png"
    _marked_picture(img, w, h)
    wav = tmp_path / "a.wav"
    nar, chars = v.voices_for(story())
    d = v.voice_panel(FakeTts(), story().panels[0], nar, chars, 30.0, wav)
    out = tmp_path / f"{name}.mp4"
    v.render_panel(img, wav, d, 30.0, "", tmp_path, False, out)
    return out, d


def test_render_panel_frame_count_is_exact(tmp_path):
    make_images(tmp_path, 1)
    wav = tmp_path / "a.wav"
    nar, chars = v.voices_for(story())
    d = v.voice_panel(FakeTts(), story().panels[0], nar, chars, 30.0, wav)
    out = tmp_path / "p.mp4"
    v.render_panel(tmp_path / "panels" / "p001.png", wav, d, 30.0, "Hello there little moon", tmp_path, True, out)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames,width,height", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert n.split(",") == ["1920", "1080", str(round(d * 30))]


@pytest.mark.parametrize("name,w,h", [("wide", 1344, 768), ("square", 1024, 1024), ("portrait", 832, 1216)])
def test_the_whole_picture_is_in_frame_and_nothing_moves(tmp_path, name, w, h):
    out, d = _render_still(tmp_path, name, w, h)
    first, last = _frame_at(out, 0.3, tmp_path / "f1.png"), _frame_at(out, d - 0.5, tmp_path / "f2.png")
    cx = 960  # the picture is centred, so its top and bottom edges are at the middle column
    top, bottom = first[6, cx], first[1073, cx]
    assert top[0] > 170 and top[2] < 100, f"{name}: the top edge of the picture is cut off ({top})"
    assert bottom[2] > 170 and bottom[0] < 100, f"{name}: the bottom edge of the picture is cut off ({bottom})"
    assert np.abs(first - last).mean() < 1.5, f"{name}: the picture moves/shakes between frames"  # encoder noise only


def _clip_from_picture(tmp_path, name, w, h, seconds=2):
    """A short 24 fps clip of a still picture (what an AI shot with almost no motion looks like), 24px red band on top, blue at the bottom."""
    img = tmp_path / f"{name}.png"
    _marked_picture(img, w, h)
    clip = tmp_path / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24", "-t", str(seconds), "-i", str(img), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    return clip


def _panel_wav(tmp_path):
    wav = tmp_path / "ai.wav"
    nar, chars = v.voices_for(story())
    return wav, v.voice_panel(FakeTts(), story().panels[0], nar, chars, 30.0, wav)


@pytest.mark.parametrize("name,w,h", [("sq", 768, 768), ("wide", 1344, 768)])
def test_ai_clip_is_shown_whole_with_the_exact_length(tmp_path, name, w, h):
    clip = _clip_from_picture(tmp_path, name, w, h)
    wav, d = _panel_wav(tmp_path)
    out = tmp_path / f"{name}_seg.mp4"
    v.render_ai_panel(clip, wav, d, 30.0, "", tmp_path, False, out)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames,width,height",
                        "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert n.split(",") == ["1920", "1080", str(round(d * 30))]
    f = _frame_at(out, 0.5, tmp_path / f"{name}.png")
    assert f[6, 960][0] > 170 and f[6, 960][2] < 100, f"{name}: the top of the shot is cut off"
    assert f[1073, 960][2] > 170 and f[1073, 960][0] < 100, f"{name}: the bottom of the shot is cut off"


def test_a_short_ai_shot_covers_a_longer_line_by_ping_pong_without_a_jump(tmp_path):
    clip = tmp_path / "moving.mp4"  # 2 s of moving test pattern at 24 fps, shorter than the 3 s the line needs
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=768x768:r=24:d=2", "-pix_fmt", "yuv420p", str(clip)], check=True)
    wav, d = _panel_wav(tmp_path)
    assert d >= 3.0
    out = tmp_path / "pp.mp4"
    v.render_ai_panel(clip, wav, d, 30.0, "", tmp_path, False, out)
    diff = lambda a, b: np.abs(_frame_at(out, a, tmp_path / "a.png") - _frame_at(out, b, tmp_path / "b.png")).mean()
    turn = diff(1.95, 2.05)   # across the turnaround at t = 2 s (the clip's end, played back from here)
    normal = diff(0.95, 1.05)  # the same 0.1 s gap in the middle of the clip
    assert turn < normal * 2 + 2, f"jump at the turnaround ({turn:.1f} vs {normal:.1f})"
    assert (tmp_path / "moving.pingpong.mp4").exists()


def test_no_shake_or_zoom_effect_exists_any_more():
    assert not hasattr(v, "MOTIONS") and not hasattr(v, "motion_filter")
    assert v.motion_fx_filters("action_shake") == []  # an unknown/removed effect adds nothing instead of wobbling the frame


def test_render_cache_key_changes_with_the_look(tmp_path, monkeypatch):
    make_images(tmp_path)
    s = story()
    v.build_video(s, tmp_path, FakeTts(), music=None)
    keys = json.loads((tmp_path / "video_meta.json").read_text())
    monkeypatch.setattr(v, "RENDER_LOOK", "something-else")
    v.build_video(s, tmp_path, FakeTts(), music=None)
    assert json.loads((tmp_path / "video_meta.json").read_text())["p001"]["render"] != keys["p001"]["render"]  # old clips are not reused


def test_build_video_total_equals_sum_of_panel_audio_and_reruns_reuse_work(tmp_path):
    make_images(tmp_path)
    s, tts = story(), FakeTts()
    out = v.build_video(s, tmp_path, tts, music=None)
    tl = json.loads((tmp_path / "timeline.json").read_text())
    assert out["panels"] == 3 and out["missing_panels"] == [] and tl["total_sec"] == pytest.approx(sum(e["duration"] for e in tl["entries"]))
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=nb_frames", "-select_streams", "v:0", "-of", "csv=p=0",
                            out["video"]], capture_output=True, text=True).stdout.strip()
    assert int(probe) == round(tl["total_sec"] * 30)
    assert (tmp_path / "story.srt").read_text().startswith("1\n00:00:00")
    calls = len(tts.calls)
    v.build_video(s, tmp_path, tts, music=None)
    assert len(tts.calls) == calls  # nothing re-voiced
    s.panels[0].caption = "A brand new first line for the story tonight."
    v.build_video(s, tmp_path, tts, music=None)
    assert len(tts.calls) == calls + 1  # only the edited panel


def test_missing_panel_images_are_reported_not_faked(tmp_path):
    make_images(tmp_path, 2)
    out = v.build_video(story(), tmp_path, FakeTts(), music=None)
    assert out["panels"] == 2 and out["missing_panels"] == ["p003"]
    with pytest.raises(ValueError):
        v.build_video(story(), tmp_path / "empty", FakeTts(), music=None)


def test_chapters_need_three_ten_second_scenes():
    s = story()
    tl = {"entries": [{"scene_id": "sc01", "start": 0.0}, {"scene_id": "sc02", "start": 12.0}]}
    assert v.chapters(s, tl) == []  # two chapters are not enough for YouTube
    s.scenes.append(Scene(id="sc03", location_id="attic", character_ids=["mira"], summary="Third.", mood="m"))
    tl["entries"].append({"scene_id": "sc03", "start": 30.0})
    ch = v.chapters(s, tl)
    assert [t for t, _ in ch] == ["0:00", "0:12", "0:30"]
