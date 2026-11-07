"""The Director: validation rules for each stage and the whole plan from one brief, with a fake model (no LLM, no GPU)."""
import asyncio

import pytest

from engine.original import director as d
from engine.original import story as sm
from engine.original.genres import GENRES

G = GENRES["explainer"]


def _bible():
    c = lambda i, n, sp, g, role, look: sm._Char(id=i, name=n, role=role, age_group="adult" if sp == "human" else "child", species=sp, gender=g, look=look, personality="curious and kind")  # noqa: E731
    return sm._Bible(characters=[c("mira", "Mira", "human", "female", "protagonist", "short copper hair, green scarf, brown jacket, red boots, round glasses"),
                                 c("pip", "Pip", "cat", "neutral", "companion", "orange tabby fur, green eyes, small white paws, blue collar, fluffy tail")],
                     locations=[sm._Loc(id="open_field", name="Open field", look="green grass, wide sky, distant hills, warm light, scattered flowers"),
                                sm._Loc(id="hilltop", name="Hilltop", look="rocky hilltop, low clouds, strong wind, grey sky, sparse grass")],
                     rules=["It is one world.", "Pip is a cat."])


def _shot(**kw):
    base = dict(framing="wide", camera="", characters=["mira", "pip"], action="Mira stands in the field and points up at the growing white clouds while Pip sits beside her.")
    return sm._Bible and d._ShotOut(**{**base, **kw})


def _take(words=34, **kw):
    return d._TakeOut(location_id="open_field", narration=" ".join(["word"] * words), shots=[_shot(), _shot(framing="close", action="The clouds grow taller and darker above the hills in the distance.")])


def test_take_count_and_fact_dealing():
    assert d.take_count(60, 15) == 4 and d.take_count(61, 15) == 5 and d.take_count(10, 15) == 1
    assert d.split_facts(list("abcdefgh"), 4) == [["a", "b"], ["c", "d"], ["e", "f"], ["g", "h"]] and d.split_facts(list("abcde"), 2) == [["a", "b", "c"], ["d", "e"]]


def test_a_good_take_passes():
    assert d.check_take(_take(), sm._Bible and _real_bible(), 15, [], G) == []


def _real_bible():
    o = _bible()
    return sm.Bible(premise=sm.Premise(title="T", genre="explainer", logline="x " * 12, tone="t", setting="s"), characters=[sm.Character(**c.model_dump()) for c in o.characters],
                    locations=[sm.Location(**x.model_dump()) for x in o.locations], rules=o.rules)


@pytest.mark.parametrize("change,needle", [
    (dict(words=5), "narration has 5 words"),
    (dict(words=80), "narration has 80 words"),
])
def test_narration_must_fit_the_take(change, needle):
    assert any(needle in p for p in d.check_take(_take(**change), _real_bible(), 15, [], G))


def test_movement_needs_a_direction_and_speech_and_text_are_refused():
    b = _real_bible()
    moving = _take()
    moving.shots[0] = _shot(action="Mira walks along the path with Pip trotting right behind her in the field.")
    assert not any("something moves" in p for p in d.check_take(moving, b, 15, [], G))  # no rejection: the Director adds the direction itself
    assert "walks to the right along the path" in moving.shots[0].action
    moving.shots[0] = _shot(action="Mira walks away from the camera along the path with Pip trotting beside her.")
    d.check_take(moving, b, 15, [], G, take_index=1)
    assert moving.shots[0].action.count("away from the camera") == 1 and "to the left" not in moving.shots[0].action  # a stated direction is kept
    talk = _take(); talk.shots[0] = _shot(action="Mira says hello to the viewer while Pip sits beside her in the field.")
    assert any("nobody speaks" in p for p in d.check_take(talk, b, 15, [], G))
    txt = _take(); txt.shots[0] = _shot(action="A big caption appears over the field while Mira and Pip look at the sky above them.")
    assert any("readable text" in p for p in d.check_take(txt, b, 15, [], G))


def test_every_character_must_be_in_the_first_shot_and_listed_when_named():
    b = _real_bible()
    t = _take()
    t.shots[0] = _shot(characters=["mira"], action="Mira stands alone in the field and points up at the growing white clouds above.")
    t.shots[1] = _shot(framing="close", characters=["mira", "pip"], action="Mira and Pip look up at the dark clouds over the hills in the distance.")
    assert any("not in shot 1" in p for p in d.check_take(t, b, 15, [], G))
    t2 = _take()
    t2.shots[1] = _shot(framing="close", characters=["mira"], action="Pip stares at the clouds above the hills while Mira watches him closely there.")
    assert any("appear in the action but are not listed" in p for p in d.check_take(t2, b, 15, [], G))
    t3 = _take(); t3.shots[0] = _shot(camera="zoom crazy")
    assert d.check_take(t3, b, 15, [], G) == [] and t3.shots[0].camera == ""  # unknown camera wording becomes a fixed camera, it is not an error


def test_direct_builds_long_takes_with_a_faceless_narrator(monkeypatch):
    class Fake:
        async def generate_structured(self, prompt, model, **kw):
            if model is d._Writer:
                return d._Writer(title="How a storm forms", logline="This video explains how a thunderstorm forms for curious teenagers. Mira and her cat Pip guide the viewer.", setting="open fields",
                                 facts=[f"Fact number {i} is a short true sentence about storms and clouds." for i in range(8)])
            if model is sm._Bible:
                return _bible()
            return _take()

    story = asyncio.run(d.direct("a one minute video on storms, a young woman and her cat", Fake(), 60))
    assert len(story.panels) == 4 and all(p.seconds == 15.0 for p in story.panels)
    assert all(p.dialogue[0].speaker_id == "narrator" and 2 <= len(p.shots) <= 3 for p in story.panels)
    assert story.panels[0].shots[0]["at"] == 0 and story.panels[0].shots[1]["at"] > 0 and [s.id for s in story.scenes] == ["s1", "s2", "s3", "s4"]
    from engine.original import film

    text = film.motion_prompt(story, story.panels[0])
    assert "[Shot 1]" in text and "[Shot 2] At 00:" in text and "exactly one woman (Mira) and exactly one cat (Pip)" in text and "Static Shot" in text


def test_requirements_of_the_brief_must_be_shown_somewhere():
    panels = [d.Panel(id="t1", scene_id="s1", shot="wide", angle="eye_level", location_id="x", character_ids=[], action="a", seconds=15,
                      shots=[{"at": 0, "framing": "wide", "camera": "", "action": "Maya points at the clouds while Pip sits beside her.", "characters": []}])]
    assert d.uncovered(["the guide walks through the landscape", "one pet cat"], panels, "Pip cat adult") == ["the guide walks through the landscape"]  # nothing walks; the cast covers the cat
    panels[0].shots.append({"at": 7.5, "framing": "wide", "camera": "", "action": "Maya walks away from the camera along the path through the hills.", "characters": []})
    assert d.uncovered(["the guide walks through the landscape"], panels) == []


def test_direct_rewrites_a_take_for_every_requirement_that_is_not_shown():
    asked = []

    class Fake:
        async def generate_structured(self, prompt, model, **kw):
            if model is d._Writer:
                return d._Writer(title="How a storm forms", logline="This video explains how a thunderstorm forms for curious teenagers. Mira guides the viewer with her cat Pip.", setting="open fields",
                                 facts=[f"Fact number {i} is a short true sentence about storms and clouds." for i in range(8)], must_show=["the guide skips rope across the meadow"])
            if model is sm._Bible:
                return _bible()
            asked.append(prompt)
            t = _take()
            if "requires this to be SEEN" in prompt:
                t.shots[0] = _shot(action="Mira skips rope toward the camera across the meadow while Pip sits beside her in the grass.")
            return t

    story = asyncio.run(d.direct("a one minute video on storms where the guide skips rope across the meadow", Fake(), 60))
    assert sum("requires this to be SEEN" in p for p in asked) == 1 and any("skips rope" in s["action"] for p in story.panels for s in p.shots)


def test_framing_and_camera_wording_maps_to_the_allowed_values():
    assert [d.normalize_framing(x) for x in ("Extreme close-up", "wide establishing shot", "medium two-shot", "weird", "Close")] == ["close", "wide", "medium", "medium", "close"]
    assert [d.normalize_camera(x) for x in ("static", "Slow push in", "pan left slowly", "tracking shot", "slow zoom out", "")] == ["", "slow push-in", "slow pan left", "", "", ""]


def test_must_show_comes_from_the_brief_and_includes_the_movement_it_asks_for():
    brief = "A one-minute video on storms. A young woman guide walks through the landscape and she has her one pet cat with her."
    ok = d._Writer(title="T", logline="x " * 12, setting="s", facts=["Fact number %d is a short true sentence about storms and clouds." % i for i in range(8)], must_show=["the guide walks through the landscape", "one pet cat"])
    assert d.check_writer(ok, 4, G, brief) == []
    made_up = ok.model_copy(update={"must_show": ["four parts"]})
    problems = d.check_writer(made_up, 4, G, brief)
    assert any("not in the owner's brief" in p for p in problems) and any("someone or something moves" in p for p in problems)
    assert d.check_writer(ok.model_copy(update={"must_show": []}), 4, G, brief)  # the walking requirement may not be dropped


def test_a_walker_needs_a_horizontal_direction_right_after_the_verb():
    assert d.needs_direction("Maya walks through the landscape, pointing upward while Pip jumps")  # 'upward' is not a way to walk
    assert not d.needs_direction("Maya walks away from the camera along the path while Pip trots beside her")
    assert not d.needs_direction("Maya walks to the left across the meadow")
    assert d.needs_direction("Maya walks along the path with Pip beside her")  # "along the path" does not say which way the camera sees her go
    assert d.needs_direction("Maya runs and Pip follows her over the hill")
    assert not d.needs_direction("A balloon floats above the field")  # only walkers need a direction
    assert not d.needs_direction("Maya stands in the field and points at the clouds")


def test_fix_direction_alternates_sides_and_leaves_stated_directions_alone():
    assert d.fix_direction("Maya walks along the path while Pip jumps", 0) == "Maya walks to the right along the path while Pip jumps"
    assert d.fix_direction("Maya walks along the path while Pip jumps", 1) == "Maya walks to the left along the path while Pip jumps"
    assert d.fix_direction("Maya runs toward the camera and Pip walks beside her", 0) == "Maya runs toward the camera and Pip walks to the right beside her"
    assert d.fix_direction("Maya points at the clouds", 0) == "Maya points at the clouds"


def test_storyboard_take_needs_one_shot_and_an_end_state_about_the_same_cast():
    b = _real_bible()
    one = d._TakeOut(location_id="open_field", narration="The growing white clouds " + " ".join(["word"] * 30), shots=[_shot()],
                     end_state="Mira and Pip stand at the right side of the frame and look up at the dark clouds.", visual="growing white clouds above the field")
    assert d.check_take(one, b, 15, [], G, storyboard=True) == []
    two = one.model_copy(update={"shots": [_shot(), _shot()]})
    assert any("exactly ONE shot" in p for p in d.check_take(two, b, 15, [], G, storyboard=True))
    assert any("end_state" in p for p in d.check_take(one.model_copy(update={"end_state": "short"}), b, 15, [], G, storyboard=True))
    solo = one.model_copy(update={"shots": [_shot(characters=["mira"], action="Mira stands in the field and points up at the growing white clouds above her.")]})
    assert any("not in the shot" in p for p in d.check_take(solo, b, 15, [], G, storyboard=True))  # the end state names Pip, who is not in the shot


def test_direct_storyboard_mode_asks_for_one_shot_with_an_end_state(monkeypatch):
    seen = []

    class Fake:
        async def generate_structured(self, prompt, model, **kw):
            seen.append(model)
            if model is d._Writer:
                return d._Writer(title="How a storm forms", logline="This video explains how a thunderstorm forms for curious teenagers. Mira and her cat Pip guide the viewer.", setting="open fields",
                                 facts=[f"Fact number {i} is a short true sentence about storms and clouds." for i in range(8)],
                                 atmosphere=[f"sky number {i} with {'dark' if i % 2 else 'bright'} clouds and {'dim' if i % 2 else 'warm'} light" for i in range(8)])
            if model is sm._Bible:
                return _bible()
            return d._BoardTake(location_id="open_field", narration="The meadow clouds " + " ".join(f"q{chr(97 + len(seen) % 26)}{chr(97 + k)}ab" for k in range(13)), visual="tall clouds above the meadow", shot=_shot(action="Mira walks to the right across the meadow under tall clouds while Pip trots beside her."),
                                end_state="Mira and Pip are at the right side of the frame and both look up at the clouds.")

    story = asyncio.run(d.direct("a one minute video on storms", Fake(), 60, 7.5, storyboard=True))
    assert len(story.panels) == 8 and d._BoardTake in seen
    p = story.panels[0]
    assert p.atmosphere.startswith("sky number 0") and story.panels[1].atmosphere != p.atmosphere
    assert len(p.shots) == 1 and p.end_state.startswith("Mira and Pip are at the right") and p.seconds == 7.5 and p.dialogue[0].speaker_id == "narrator"


def test_characters_are_never_carried_by_or_perched_on_each_other():
    names = ["Maya", "Luna"]
    assert d.stacked("Maya stands on the left while Luna sits on her right shoulder watching the rain.", names) == "Luna"
    assert d.stacked("Maya carries Luna across the stream", names) == "Maya" or d.stacked("Maya carries Luna across the stream", names) == "Luna"
    assert d.stacked("Maya holds a glowing crystal and Luna sits beside her on the grass", names) is None
    b = _real_bible()
    t = _take()
    t.shots[0] = _shot(action="Mira stands in the field while Pip sits on her right shoulder and watches the clouds above them.")
    assert any("carried by or sits on another character" in p for p in d.check_take(t, b, 15, [], G))


def test_walks_walked_and_walking_are_one_word_and_a_walker_must_be_shown_walking():
    assert d.content_words("the guide walks") == d.content_words("she walked") == d.content_words("walking")
    only_said = [d.Panel(id="t1", scene_id="s1", shot="wide", angle="eye_level", location_id="x", character_ids=[], action="a", seconds=7.5,
                         shots=[{"at": 0, "framing": "wide", "camera": "", "action": "Maya stands in the field while the cat sits beside her.", "characters": []}], end_state="Maya has walked slowly to the right.")]
    assert d.uncovered(["the guide walks through the landscape"], only_said) == ["the guide walks through the landscape"]  # 'has walked' in an END state is not walking on screen
    only_said[0].shots[0]["action"] = "Maya walks to the right across the field while the cat sits beside her."
    assert d.uncovered(["the guide walks through the landscape"], only_said) == []


def test_writer_must_plan_a_different_sky_for_every_part_in_storyboard_mode():
    from engine.original import director as d
    from engine.original.director import GENRES

    w = d._Writer(title="T", logline="A guide explains how storms build up over a valley, for curious children everywhere.", setting="a valley",
                  facts=["Warm air rises from the sunny ground and cools as it climbs higher."] * 2, atmosphere=["bright blue sky with warm sunshine", "bright blue sky with warm sunshine"])
    g = GENRES["explainer"]
    assert any("atmosphere" in p for p in d.check_writer(w, 2, g, "", True))
    assert not any("atmosphere" in p for p in d.check_writer(w, 2, g, "", False))  # not asked for outside storyboard mode
    w.atmosphere = ["bright blue sky with warm sunshine", "towering dark clouds gather and the light turns grey"]
    assert not any("atmosphere" in p for p in d.check_writer(w, 2, g, "", True))


def test_storyboard_take_must_show_its_fact_and_say_what_is_seen():
    t = d._TakeOut(location_id="open_field", narration="Look at that huge dark anvil cloud: warm wet air rose and cooled into it.", shots=[_shot(action="A huge dark anvil cloud towers over the hills while Mira points at it from the left.")],
                   end_state="Mira stands at the left side of the frame and looks up at the cloud with Pip.", visual="a huge dark anvil cloud over the hills")
    assert d.picture_first(t) == []
    assert any("mention the visual" in p for p in d.picture_first(t.model_copy(update={"narration": "Ice crystals collide inside and build up electric charge over time."})))
    assert any("repeats" in p for p in d.picture_first(t, prev=t.narration))


def test_a_character_on_another_characters_back_is_stacked_even_far_from_the_name():
    assert d.stacked("pip on the right side of the frame jumping to her back as wind bends grass", ["Elara", "Pip"]) == "Pip"
    assert d.stacked("Elara turns her back to the camera while Pip sits on the grass", ["Elara", "Pip"]) is None


def test_character_ids_tolerate_the_models_wording():
    chars = {c.id: c for c in _real_bible().characters}
    assert d.character_id("Mira: center facing right", chars) == "mira" and d.character_id(" PIP ", chars) == "pip" and d.character_id("dragon", chars) == "dragon"
    assert d.character_id("mira stands center-left pointing at the sky", chars) == "mira"
