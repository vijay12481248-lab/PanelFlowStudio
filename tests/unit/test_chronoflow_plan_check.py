"""The Video Plan: tolerant reader, checker, and the kit the owner hands to a chatbot (the kit must embed exactly the code and example the app uses)."""
import copy
import json
import re
from pathlib import Path

import pytest

from engine.chronoflow import plan_check as pc

KIT_DIR = Path(pc.__file__).parent / "plan_kit"
KIT = KIT_DIR / "PANELFLOW_VIDEO_PLAN_KIT.md"
EXAMPLE = json.loads((KIT_DIR / "example_plan.json").read_text(encoding="utf-8"))


def good():
    return copy.deepcopy(EXAMPLE)


def test_example_plan_has_no_problems():
    assert pc.check(good()) == []


# ---- reader: what chatbots really send back
BODY = json.dumps(EXAMPLE, indent=2)


@pytest.mark.parametrize("wrap", [
    lambda s: s,
    lambda s: "```json\n" + s + "\n```",
    lambda s: "Here is your plan:\n\n```\n" + s + "\n```\n\nSave it as plan.json.",
    lambda s: "﻿" + s,
    lambda s: s.replace('"Why Do Rainbows Appear?"', "“Why Do Rainbows Appear?”"),
    lambda s: s.replace('"t04",', '"t04",').replace("}\n  ]\n}", "},\n  ]\n}"),  # trailing comma after the last take
])
def test_reader_accepts_real_world_wrappers(wrap):
    assert pc.read_plan(wrap(BODY))["title"] == "Why Do Rainbows Appear?"


@pytest.mark.parametrize("text, hint", [("", "empty"), ("no json here", "JSON"), ('{"a": ', "line"), ("[1, 2]", "object")])
def test_reader_failures_say_what_is_wrong(text, hint):
    with pytest.raises(ValueError) as e:
        pc.read_plan(text)
    assert hint.lower() in str(e.value).lower()


# ---- checker: each rule bites
def mutate(fn):
    p = good()
    fn(p)
    return pc.check(p)


@pytest.mark.parametrize("fn, expect", [
    (lambda p: p.update(panelflow_plan=1), "panelflow_plan"),
    (lambda p: p.update(target="short"), "target"),
    (lambda p: p.update(title=""), "title"),
    (lambda p: p.update(genre="western"), "genre"),
    (lambda p: p["production"].update(clip_seconds=1), "clip_seconds"),
    (lambda p: p["production"].update(total_seconds=100), "add up"),
    (lambda p: p["takes"][0].update(seconds=9), "seconds"),
    (lambda p: p["takes"][0].update(narration="Too short."), "narration has 2 words"),
    (lambda p: p["takes"][1].update(start_picture="Mira stands somewhere in the meadow doing nothing much at all."), "start_picture must be left out"),
    (lambda p: p["takes"][0].update(start_from="previous_end"), "first take of every scene"),
    (lambda p: p["takes"][1].update(motion="Mira walks across the meadow while Pip follows slowly behind her."), "direction"),
    (lambda p: p["takes"][1].update(motion="Mira runs to the right and nothing else is in the meadow at all."), "never name what must not appear"),
    (lambda p: p["takes"][0].update(motion="Mira looks up at the clouds while Pip tilts its head to the side."), "direction"),
    (lambda p: p["takes"][0].update(end_picture="Mira holds the prism."), "end_picture needs at least 8 words"),
    (lambda p: p["takes"][3].update(shows="x"), "shows"),
    (lambda p: p["takes"][0].update(cast=["mira", "ghost"]), "ghost"),
    (lambda p: p["cast"][0].update(look="a young woman with copper hair and a green scarf"), "comma-separated"),
    (lambda p: p["takes"][0].update(camera="whip pan"), "camera"),
    (lambda p: p["takes"][0].update(start_picture="Mira stands on the left holding a sign reading RAINBOW with Pip sitting beside her."), "readable text"),
    (lambda p: p["takes"][0].update(beats=[{"at": 0, "action": "Mira looks up at the clouds above"}]), "beats are only for"),
    (lambda p: p["production"].update(join="seamless_chain"), "seamless_chain"),
])
def test_checker_catches(fn, expect):
    found = mutate(fn)
    assert any(expect.lower() in m.lower() for m in found), (expect, found)


def test_a_take_that_features_a_character_not_in_its_cast_is_caught():
    found = mutate(lambda p: p["takes"][2].update(cast=["mira"]))
    assert any("Pip" in m and "not in this take's cast" in m for m in found), found


def test_beats_are_accepted_for_long_clips():
    p = good()
    p["production"].update(clip_seconds=10, total_seconds=40)
    for t in p["takes"]:
        t["seconds"] = 10
        t["narration"] = "After the rain has stopped, bright sunlight breaks through the thinning clouds above the green meadow today."
    p["takes"][0]["beats"] = [{"at": 0, "action": "Mira looks up at the grey clouds above the meadow"}, {"at": 5, "action": "Mira points at the bright sunlight breaking through"}]
    found = [m for m in pc.check(p) if "narration" not in m]
    assert found == [], found


# ---- the kit the owner gives away must carry exactly what the app runs
def blocks():
    return re.findall(r"```(json|python)\n(.*?)\n```", KIT.read_text(encoding="utf-8"), re.S)


def test_kit_embeds_the_example_the_app_uses():
    assert json.loads(blocks()[0][1]) == EXAMPLE


def test_kit_embeds_exactly_the_checker_the_app_runs():
    assert blocks()[2][1].strip() == Path(pc.__file__).read_text(encoding="utf-8").strip()


def test_kit_short_example_has_exactly_the_keys_of_a_shipped_reel():
    from tools.reels import specs

    short = json.loads(blocks()[1][1])["short"]
    shipped = specs.REELS[0]
    assert sorted(short) == sorted(shipped) and all(sorted(s) == sorted(shipped["scenes"][0]) for s in short["scenes"]) and len(short["scenes"]) == 5


# ---- v2 tightening: every take is two pictures; the app has no clip-tail start
@pytest.mark.parametrize("fn, expect", [
    (lambda p: p["takes"][0].pop("end_picture"), "end_picture needs at least 8 words"),
    (lambda p: p["production"].update(join="clip_tail"), "production.join"),
    (lambda p: p["takes"][1].update(start_from="clip_tail"), "start_from"),
])
def test_checker_v2_rules(fn, expect):
    found = mutate(fn)
    assert any(expect.lower() in m.lower() for m in found), (expect, found)
