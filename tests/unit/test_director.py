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
    assert any("which way relative to the camera" in p for p in d.check_take(moving, b, 15, [], G))
    moving.shots[0] = _shot(action="Mira walks away from the camera along the path with Pip trotting beside her.")
    assert not any("which way" in p for p in d.check_take(moving, b, 15, [], G))
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
    assert any("camera must be empty" in p for p in d.check_take(t3, b, 15, [], G))


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
