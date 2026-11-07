"""Storyboard approach: start/end pictures per shot (same seed, walk sides, chained shots, cast-count redraws), FL2VA clip prompts - with a fake art runner and VLM (no GPU)."""
import asyncio
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.original import film
from engine.original import storyboard as sb

SRC = Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py"


@pytest.fixture(scope="module")
def story():
    spec = importlib.util.spec_from_file_location("dg", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.story


def _png(v=100):
    return cv2.imencode(".png", np.full((48, 64, 3), v, np.uint8))[1].tobytes()


def _panel(story, i=0, **kw):
    p = story.panels[i]
    return p.model_copy(update={"seconds": 7.5, "shots": [], "end_state": "Mira stands at the far right of the frame and looks up at the sky while Pip floats beside her.", **kw})


def test_walk_direction_and_sides(story):
    assert sb.walk_direction(_panel(story, action="Mira walks to the right along the path")) == "right"
    assert sb.walk_direction(_panel(story, action="Mira walks to the left", end_state="Mira stands")) == "left"
    assert sb.walk_direction(_panel(story, action="Mira stands", end_state="she waits")) is None
    assert sb.sides(2, "right", "start") == ["left", "center"] and sb.sides(2, "right", "end") == ["center", "right"]
    assert sb.sides(1, "right", "start") == ["left"] and sb.sides(1, "left", "end") == ["left"] and sb.sides(1, "left", "start") == ["right"]
    assert sb.sides(3, "right", "end") is None and sb.sides(2, None, "end") is None


def test_keyframe_prompts_use_the_start_action_and_the_end_state(story):
    p = _panel(story, action="Mira walks to the right along the path while Pip floats beside her", character_ids=["mira", "pip"])
    start, _ = sb.keyframe_prompt(story, p, "start")
    end, _ = sb.keyframe_prompt(story, p, "end")
    assert start != end and "far right" in end.lower() or "right" in end.lower()
    assert "walks to the right" in start and "walks to the right" not in end


def test_a_shot_that_continues_starts_from_the_previous_end(story):
    a = _panel(story, 0)
    b = a.model_copy(update={"id": "x2"})
    assert sb.continues(a, b) and not sb.continues(None, b)
    assert not sb.continues(a, b.model_copy(update={"location_id": "somewhere_else"})) and not sb.continues(a, b.model_copy(update={"character_ids": ["mira"]}))
    assert not sb.continues(a.model_copy(update={"end_state": ""}), b)


def test_draw_uses_one_seed_per_shot_chains_and_redraws_a_wrong_count(story, tmp_path, monkeypatch):
    p1 = _panel(story, 0, id="a1", character_ids=["mira", "pip"], action="Mira stands in the field with Pip beside her")
    p2 = p1.model_copy(update={"id": "a2"})
    st = story.model_copy(update={"panels": [p1, p2]})
    seeds, names = [], []

    class Runner:
        def generate(self, pos, neg, seed, w, h, prefix):
            seeds.append(seed)
            names.append(prefix)
            return _png(len(seeds) * 7 % 250)

    calls = {"n": 0}

    class Provider:  # the first picture of a1 shows 2 girls (planned 1): one redraw; everything else matches
        async def analyze_vision(self, png, prompt, **kw):
            calls["n"] += 1
            return json.dumps({"count": 2 if calls["n"] <= 2 and "girls" in prompt else 1})

    rep = asyncio.run(sb.draw(st, tmp_path, Runner(), Provider(), tries=3, progress=lambda m: None))
    assert rep["a1"]["attempts"] == 2 and not rep["a1"]["problems"] and rep["a2"]["chained"] is True and rep["a2"]["attempts"] == 1
    a1 = [(n, s) for n, s in zip(names, seeds) if n.startswith("sb_a1")]
    assert a1[0][1] == a1[1][1] and a1[2][1] == a1[3][1] and a1[0][1] != a1[2][1]  # start and end share a seed; a redraw uses a new one
    fd = tmp_path / "film" / "frames"
    assert (fd / "a2.png").read_bytes() == (fd / "a1_end.png").read_bytes()  # the second shot starts from the first shot's end picture
    assert not any(n.startswith("sb_a2_start") for n in names)  # and was not drawn again


def test_clip_prompt_pins_the_cast_the_camera_and_the_ending(story):
    p = _panel(story, 0, character_ids=["mira", "pip"], action="Mira walks to the right across the meadow")
    text = sb.clip_prompt(story, p, 7.5)
    assert text.startswith("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark")
    assert "exactly one girl (Mira)" in text and "no other people or animals appear" in text and "Static Shot" in text and "The last picture shows: Mira stands at the far right" in text


def test_make_clips_anchors_silence_and_lands_between_the_two_pictures(story, tmp_path, monkeypatch):
    p = _panel(story, 0, id="m1", character_ids=["mira"], dialogue=[film.Line(speaker_id="narrator", text="Warm air rises from the ground and carries moisture up.")]) if hasattr(film, "Line") else None
    from engine.original.models import Line

    p = _panel(story, 0, id="m1", character_ids=["mira"], dialogue=[Line(speaker_id="narrator", text="Warm air rises from the ground.")])
    st = story.model_copy(update={"panels": [p]})
    fd = film.film_dir(tmp_path)
    (fd / "frames" / "m1.png").write_bytes(_png(50))
    (fd / "frames" / "m1_end.png").write_bytes(_png(60))
    seen = {}

    def fake_voice(story_, ws, panel, tts, voices):
        wav = ws / "film" / "voice" / f"{panel.id}.wav"
        wav.write_bytes(b"x")
        return wav, 3.0

    def fake_silent(ws, panel, seconds=None):
        w = ws / "film" / "voice" / f"{panel.id}.silent.wav"
        w.write_bytes(b"s")
        return w, seconds

    def fake_clip(mode, prompt, **kw):
        seen.update(mode=mode, **kw)
        return b"mp4"

    from engine.narration.runtime import audio as rt

    monkeypatch.setattr(rt, "KokoroTts", lambda: object())
    monkeypatch.setattr(film, "voice_shot", fake_voice)
    monkeypatch.setattr(film, "silent_shot", fake_silent)
    monkeypatch.setattr(sb.h3_modes, "make_clip", fake_clip)
    monkeypatch.setattr(film, "clip_stats", lambda path: {"frames": 1})
    import engine.original.animate as an

    monkeypatch.setattr(an, "release_ollama", lambda: None)
    res = sb.make_clips(st, tmp_path, progress=lambda m: None)
    assert res["made"] == ["m1"] and seen["mode"] == "fl2va" and seen["first"].name == "m1.png" and seen["last"].name == "m1_end.png" and seen["voice"].name == "m1.silent.wav"
    assert seen["seconds"] == pytest.approx(film.snap_frames(7.5) / film.FPS)
    assert sb.make_clips(st, tmp_path, progress=lambda m: None)["reused"] == ["m1"]  # unchanged inputs: reused


def test_a_walker_is_drawn_in_the_far_third_at_the_start_and_the_near_third_at_the_end(story):
    p = _panel(story, action="Mira walks to the right along the path", character_ids=["mira"])
    assert "in the left third of the frame" in sb.third_of_frame(story, p, "start") and "in the right third of the frame" in sb.third_of_frame(story, p, "end")
    assert sb.third_of_frame(story, _panel(story, action="Mira stands"), "start") == ""


def test_a_bad_end_picture_is_not_chained_into_the_next_shot(story, tmp_path):
    p1 = _panel(story, 0, id="b1", character_ids=["mira", "pip"], action="Mira stands in the field with Pip beside her")
    p2 = p1.model_copy(update={"id": "b2"})
    st = story.model_copy(update={"panels": [p1, p2]})

    class Runner:
        def generate(self, *a):
            return _png(90)

    class Provider:
        async def analyze_vision(self, png, prompt, **kw):
            return json.dumps({"count": 3 if "sky-fox" in prompt else 1})  # the cat count is always wrong: the end picture of b1 can never pass

    rep = asyncio.run(sb.draw(st, tmp_path, Runner(), Provider(), tries=2, progress=lambda m: None))
    assert rep["b1"]["problems"] and rep["b2"]["chained"] is False


def test_every_character_is_described_once_so_the_model_draws_one_cat():
    names = {"maya": "Maya", "miso": "Miso"}
    mine, others = sb.split_actions("Maya stands center-left holding her umbrella while Miso sits on a rock to her right, looking at a bright flash of lightning", names, "maya")
    assert "Miso" not in mine and "umbrella" in mine and others == {"miso": "sits on a rock to her right, looking at a bright flash of lightning"}
    mine, others = sb.split_actions("Maya and Miso stand on the left side looking up; Maya reaches upward as the droplets sparkle", names, "maya")
    assert "Miso" in mine and others == {}  # a clause about both stays with the first character
    mine, others = sb.split_actions("Maya stands center; Miso walks from left to right", names, "maya")
    assert mine == "Maya stands center" and others == {"miso": "walks from left to right"}


def test_the_keyframe_prompt_mentions_the_cat_only_in_its_own_entry(story):
    p = _panel(story, 0, character_ids=["mira", "pip"], action="Mira stands center-left while Pip sits on a rock to her right and watches the lightning")
    start, _ = sb.keyframe_prompt(story, p, "start")
    assert start.lower().count("on a rock") == 1  # once, in Pip's entry (not again in Mira's)


def test_clip_prompt_keeps_everyone_in_frame_and_the_camera_still(story):
    text = sb.clip_prompt(story, _panel(story, 0, character_ids=["mira", "pip"]), 8.0)
    assert "Everyone stays inside the frame for the whole shot" in text and "The camera never tilts, pans or moves" in text and "background stays calm and steady" in text


def test_clip_prompt_does_not_send_the_story_events_only_a_gradual_change(story):
    p = _panel(story, 0, character_ids=["mira"], action="A massive blue lightning bolt arcs down while the sky explodes")
    text = sb.clip_prompt(story, p, 8.0)
    assert "lightning" not in text and "changes gradually and smoothly from the first picture into the last picture" in text and "only a little" in text
    walk = sb.clip_prompt(story, _panel(story, 0, character_ids=["mira"], action="Mira walks to the right across the meadow"), 8.0)
    assert "walks to the right across the frame, in profile" in walk


def test_a_walker_must_end_on_the_other_side(story, tmp_path):
    from engine.original import clip_identity as ci

    assert ci.walk_ok("right", "left", "right") == [] and ci.walk_ok("right", "left", "center") == [] and ci.walk_ok("left", "right", "left") == []
    assert ci.walk_ok("right", "left", "left") and ci.walk_ok("right", "right", "left") and ci.walk_ok("left", "center", "right")
    assert ci.walk_ok("right", None, "right") == []  # unknown is not a problem
    p1 = _panel(story, 0, id="w1", character_ids=["mira"], action="Mira walks to the right across the meadow")
    st = story.model_copy(update={"panels": [p1]})

    class Runner:
        def generate(self, *a):
            return _png(90)

    class Provider:  # the girl is on the left in both pictures: the walk is not drawn
        async def analyze_vision(self, png, prompt, **kw):
            return json.dumps({"side": "left"} if "left third" in prompt or "mostly on the left" in prompt else {"count": 1})

    rep = asyncio.run(sb.draw(st, tmp_path, Runner(), Provider(), tries=2, progress=lambda m: None))
    assert rep["w1"]["attempts"] == 2 and rep["w1"]["problems"].get("walk")


def test_the_end_picture_keeps_the_start_scenery_and_only_moves_the_characters(story):
    p = _panel(story, 0, character_ids=["mira", "pip"], action="Mira stands on the left looking up; dark clouds swirl overhead and a bolt flashes in the distance",
               end_state="Mira walks to the right side of the frame; the sky is clear and calm")
    text = sb.end_text(story, p)
    assert "Mira walks to the right side" in text and "dark clouds swirl overhead" in text and "bolt flashes" in text and "clear and calm" not in text
    assert sb.end_text(story, _panel(story, 0, action="dark clouds", end_state="the sky clears")) == "the sky clears"  # no character clause at all: keep the end state as written


def test_the_clip_prompt_names_only_the_characters_end_places(story):
    p = _panel(story, 0, character_ids=["mira"], action="Mira stands left; clouds swirl", end_state="Mira stands on the right side; a lightning bolt strikes behind her")
    text = sb.clip_prompt(story, p, 8.0)
    assert "The last picture shows: Mira stands on the right side" in text and "lightning bolt" not in text and "smoke" not in text.lower() and "dust" not in text.lower() and "glow" not in text.lower() and "ring" not in text.lower().replace("bring","").replace("string","")


def test_a_walker_does_not_start_from_an_end_picture_on_the_side_it_walks_to(story, tmp_path):
    a = _panel(story, 0, id="c1", character_ids=["mira"], action="Mira walks to the right across the meadow", end_state="Mira is on the right side of the frame")
    b = a.model_copy(update={"id": "c2"})
    st = story.model_copy(update={"panels": [a, b]})
    drawn = []

    class Runner:
        def generate(self, pos, neg, seed, w, h, prefix):
            drawn.append(prefix)
            return _png(90)

    class Provider:  # the girl is on the RIGHT in every picture
        async def analyze_vision(self, png, prompt, **kw):
            return json.dumps({"side": "right"} if "third" in prompt or "mostly on" in prompt else {"count": 1})

    asyncio.run(sb.draw(st, tmp_path, Runner(), Provider(), tries=1, progress=lambda m: None))
    assert "sb_c2_start" in drawn  # c2 walks right but c1 ended on the right: it is drawn fresh, not chained


def test_a_seated_animal_to_the_right_is_not_a_walk_but_a_walker_is(story):
    assert sb.walk_direction(_panel(story, action="Maya stands left while Ziggy sits on a rock to the right", end_state="Maya points at the sky")) is None
    assert sb.walk_direction(_panel(story, action="Maya walks slowly to the right across the field", end_state="")) == "right"
    assert sb.walk_direction(_panel(story, action="Ziggy walks from right to left beside her", end_state="")) == "left"
    assert sb.walk_direction(_panel(story, action="Maya walks to the right while Ziggy walks to the left", end_state="")) is None  # two walkers going opposite ways: leave the layout alone


def test_the_planned_sky_is_in_both_pictures_of_a_shot(story):
    p = _panel(story, action="Mira stands on the hill and points at the horizon", character_ids=["mira"], atmosphere="heavy dark grey clouds cover the sky and the light turns dim and cold")
    for which in ("start", "end"):
        assert "dark grey clouds" in sb.keyframe_prompt(story, p, which)[0]
    assert "dark grey clouds" not in sb.keyframe_prompt(story, p.model_copy(update={"atmosphere": ""}), "start")[0]
