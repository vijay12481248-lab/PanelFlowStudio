import asyncio

import pytest

from engine.original import story as st
from engine.original.genres import GENRES
from engine.original.models import Bible, Character, Location, Premise, Scene

BED, HORROR = GENRES["bedtime"], GENRES["horror"]


def bible(**kw):
    chars = kw["chars"] if "chars" in kw else [
        st._Char(id="mira", name="Mira", role="protagonist", age_group="child",
                 look="short brown hair, green eyes, yellow raincoat, red boots", personality="curious"),
        st._Char(id="pip", name="Pip", role="companion", age_group="child",
                 look="small grey owl, big round eyes, tiny scarf, soft feathers", personality="kind")]
    locs = [st._Loc(id="attic", name="The Attic", look="dusty, wooden beams, round window, warm lamp"),
            st._Loc(id="garden", name="Moon Garden", look="silver flowers, night sky, fireflies, stone path")]
    return st._Bible(characters=chars, locations=locs, rules=["The lamp never goes out."])


def full_bible():
    b = bible()
    return Bible(premise=Premise(title="Mira and the Moon", genre="bedtime", logline="l", tone="t", setting="s"),
                 characters=[Character(**c.model_dump()) for c in b.characters],
                 locations=[Location(**x.model_dump()) for x in b.locations], rules=b.rules)


def test_valid_bible_passes_and_problems_are_reported():
    assert st.check_bible(bible(), BED) == []
    bad = bible(chars=[st._Char(id="Bad Id", name="X", role="antagonist", age_group="adult", look="one tag", personality="p"),
                       st._Char(id="hero", name="H", role="protagonist", age_group="adult", look="a, b, c, d", personality="p")])
    msg = " ".join(st.check_bible(bad, BED))
    for needle in ("4 comma", "must be a child", "no antagonist"):
        assert needle in msg
    adult_hero = bible(chars=[st._Char(id="a", name="A", role="protagonist", age_group="adult", look="a, b, c, d", personality="p"),
                              st._Char(id="b", name="B", role="companion", age_group="child", look="a, b, c, d", personality="p")])
    assert any("must be a child" in m for m in st.check_bible(adult_hero, BED))


def test_forbidden_words_depend_on_genre():
    assert st.forbidden_hits("a bloody knife", BED) == ["bloody", "knife"]
    assert st.forbidden_hits("a bloody knife", HORROR) == ["bloody"]
    assert "sex" in st.forbidden_hits("sex", HORROR)


def test_unknown_names_catch_invented_people_not_sentence_starts():
    allowed = st.known_names(full_bible())
    assert st.unknown_names("Then Mira meets Zorblax in the Attic.", allowed) == ["Zorblax"]
    assert st.unknown_names("Quietly, Mira smiles at Pip.", allowed) == []


def sc():
    return Scene(id="sc01", location_id="attic", character_ids=["mira", "pip"], summary="x", mood="calm")


CAP = " ".join(["soft"] * 30)


def panel(**kw):
    base = dict(shot="wide", angle="eye_level", character_ids=["mira"], action="Mira stands in the dusty attic holding a lamp",
                dialogue=[], caption=CAP, sfx=[])
    return st._PanelOut(**{**base, **kw})


def test_panel_rules():
    good = st._Panels(panels=[panel(), panel(shot="medium", dialogue=[st._LineOut(speaker_id="mira", text="Hello Pip!")]),
                              panel(shot="close", character_ids=["pip"]), panel(shot="wide")])
    assert st.check_panels(good, sc(), full_bible(), BED) == []
    bad = st._Panels(panels=[panel(shot="medium", character_ids=["ghost"], dialogue=[st._LineOut(speaker_id="pip", text="word " * 30)],
                                   action='"Hi" says Bob', caption="Zorblax appears here")])
    msg = " ".join(st.check_panels(bad, sc(), full_bible(), BED))
    for needle in ("panels, got", "wide establishing", "character_ids must be", "6+ words", "not shown", "1-18 words", "unknown names", "caption must be"):
        assert needle in msg


class ScriptedLLM:
    """Plays a canned, valid story; optionally makes the first answer to a step invalid."""

    def __init__(self, break_first=None):
        self.break_first, self.calls = break_first, {}
        self.prompts = []

    async def generate_structured(self, prompt, model, **kw):
        self.prompts.append(prompt)
        n = self.calls[model.__name__] = self.calls.get(model.__name__, 0) + 1
        if model is st._Premise:
            return model(title="Mira and the Moon", logline="Mira cannot sleep because the moon looks lonely. "
                         "She and Pip carry a lantern to keep it company.", setting="a quiet attic house")
        if model is st._Bible:
            return bible()
        if model is st._Outline:
            k = BED.scenes
            return model(scenes=[st._SceneOut(location_id="attic" if i % 2 else "garden", character_ids=["mira", "pip"],
                                              summary="Mira and Pip talk about the moon and decide to help it feel less alone.",
                                              mood="calm") for i in range(k)])
        if self.break_first == "panels" and n == 1:
            return model(panels=[panel(shot="medium")])
        return model(panels=[panel(), panel(shot="medium", dialogue=[st._LineOut(speaker_id="mira", text="The moon looks sleepy.")]),
                             panel(shot="close", character_ids=["pip"]), panel(shot="medium")])


def test_generate_story_end_to_end_with_fake_llm():
    s = asyncio.run(st.generate_story("bedtime", ScriptedLLM()))
    assert len(s.scenes) == BED.scenes and len(s.panels) == 4 * BED.scenes
    assert [p.id for p in s.panels][:2] == ["p001", "p002"] and s.panels[0].scene_id == "sc01"
    assert all(p.location_id in {"attic", "garden"} for p in s.panels)
    assert st.estimated_minutes(s) > 0


def test_bad_step_is_retried_with_the_concrete_problems():
    llm = ScriptedLLM(break_first="panels")
    asyncio.run(st.generate_story("bedtime", llm))
    assert any("Your last answer had these problems" in p and "wide establishing" in p for p in llm.prompts)


def test_continuity_warnings():
    s = asyncio.run(st.generate_story("bedtime", ScriptedLLM()))
    s.panels = [p.model_copy(update={"character_ids": ["mira"]}) for p in s.panels]
    assert any("Pip never appears" in w for w in st.continuity_warnings(s))


def test_gives_up_after_retries():
    class Bad(ScriptedLLM):
        async def generate_structured(self, prompt, model, **kw):
            return bible(chars=[]) if model is st._Bible else await super().generate_structured(prompt, model, **kw)
    with pytest.raises(ValueError, match="failed validation"):
        asyncio.run(st.generate_story("bedtime", Bad()))


def test_cosmetic_model_mistakes_are_normalised_not_rejected():
    b = st._Bible(characters=[
        st._Char(id="Moon-Kite", name="Moon Kite", role="Companion", age_group="ageless", look="a, b, c, d, e", personality="p"),
        st._Char(id="Mira", name="Mira", role="protagonist", age_group="Kid", look="a, b, c, d, e", personality="p")],
        locations=[st._Loc(id="attic-window-view", name="Attic", look="a, b, c, d"), st._Loc(id="garden", name="G", look="a, b, c, d")],
        rules=["r"])
    assert st.check_bible(b, BED) == []
    assert [c.id for c in b.characters] == ["moon_kite", "mira"] and b.characters[1].age_group == "child"
    assert b.characters[0].age_group == "adult" and b.locations[0].id == "attic"


def test_names_and_variants_resolve_to_ids_in_outline_and_panels():
    bb = full_bible()
    o = st.normalize_panels(st._Panels(panels=[panel(character_ids=["Mira", "PIP"], shot="Over Shoulder",
                                                     dialogue=[st._LineOut(speaker_id="Pip", text="Hi")])]), bb)
    x = o.panels[0]
    assert x.character_ids == ["mira", "pip"] and x.shot == "over_shoulder" and x.dialogue[0].speaker_id == "pip"


def test_missing_or_extra_protagonists_and_duplicate_ids_are_repaired():
    mk = lambda i, n, r: st._Char(id=i, name=n, role=r, age_group="adult", look="a, b, c, d", personality="p")
    b = st._Bible(characters=[mk("Ann", "Ann", "other"), mk("ann", "Ann 2", "companion")],
                  locations=[st._Loc(id="x", name="X", look="a, b, c, d"), st._Loc(id="x", name="Y", look="a, b, c, d")], rules=[])
    assert st.check_bible(b, HORROR) == []
    assert [c.role for c in b.characters] == ["protagonist", "companion"]
    assert len({x.id for x in b.characters + b.locations}) == 4


def test_unknown_names_alone_become_a_warning_after_two_tries():
    class P:
        calls = 0

        async def generate_structured(self, prompt, model, **kw):
            P.calls += 1
            return st._Outline(scenes=[st._SceneOut(location_id="attic", character_ids=["mira"], mood="m",
                                                    summary="Mira polishes the Fresnel lens in the attic every single night.")] * BED.scenes)
    notes = []
    out = asyncio.run(st._ask(P(), "p", st._Outline, lambda o: st.check_outline(o, full_bible(), BED), notes=notes))
    assert P.calls == 2 and notes and "Fresnel" in notes[0] and len(out.scenes) == BED.scenes


def test_pronouns_are_not_character_names():
    b = bible(chars=[st._Char(id="they", name="They", role="protagonist", age_group="elder", look="a, b, c, d", personality="p"),
                     st._Char(id="it", name="It", role="other", age_group="adult", look="a, b, c, d", personality="p")])
    assert sum("proper name" in m for m in st.check_bible(b, HORROR)) == 2
