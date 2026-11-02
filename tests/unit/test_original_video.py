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


def test_render_panel_frame_count_is_exact_for_every_motion(tmp_path):
    make_images(tmp_path, 1)
    wav = tmp_path / "a.wav"
    nar, chars = v.voices_for(story())
    d = v.voice_panel(FakeTts(), story().panels[0], nar, chars, 30.0, wav)
    for m in v.MOTIONS:
        out = tmp_path / f"{m}.mp4"
        v.render_panel(tmp_path / "panels" / "p001.png", wav, d, 30.0, "Hello there little moon", m, tmp_path, True, out)
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames,width,height", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        assert n.split(",") == ["1920", "1080", str(round(d * 30))], m


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
