"""Task 3 of the scene-director plan: propose a plan from a vague brief, ask few questions, apply the owner's corrections. Fake provider, no GPU."""
import asyncio

import pytest

from engine.original.scene_plan import load_playbook, validate_plan
from engine.original.scene_planner import (
    MAX_BRIEF_CHARS, Proposal, apply_corrections, classify_scene_type, plan_to_words, propose,
)


class FakeProvider:
    """Answers each structured call from a queue of canned dicts and records what was asked."""

    def __init__(self, *answers: dict):
        self.answers = list(answers)
        self.calls: list[str] = []

    async def generate_structured(self, text, model, **kw):
        self.calls.append(text)
        return self.answers.pop(0)


FIGHT_ANSWER = {
    "actors": [{"id": "hero", "description": "young swordsman", "side": "left", "action_state": "striking"},
               {"id": "villain", "description": "armoured warlord", "side": "right", "action_state": "blocking"}],
    "contacts": [{"source": "hero", "target": "villain", "body_part": "sword", "direction": "down-right"}],
    "camera": {"angle": "eye_level", "distance": "wide"},
    "light": {"direction": "front"},
    "mood": "tense", "setting": "a stone courtyard",
}


def run(coro):
    return asyncio.run(coro)


def test_propose_fills_defaults_and_marks_assumed():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain"))
    assert isinstance(p, Proposal)
    pb = load_playbook("fight")
    assert validate_plan(p.plan, pb) == []
    assert p.plan.camera.angle == pb.defaults["camera"]["angle"]  # not stated -> playbook default
    assert p.plan.light.direction == pb.defaults["light"]["direction"]
    assert {"camera.angle", "light.direction", "actors.hero.action_state"} <= set(p.plan.assumed)


def test_questions_are_capped_at_three_and_high_impact_only():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain"))
    assert 0 < len(p.questions) <= 3
    assert all(q.default and q.text for q in p.questions)
    assert {q.field for q in p.questions} <= {"camera.angle", "light.direction", "actors.hero.action_state", "actors.villain.action_state"}


def test_stated_items_are_not_asked():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain, seen from below, backlit"))
    assert "camera.angle" not in {q.field for q in p.questions}
    assert "light.direction" not in {q.field for q in p.questions}
    assert "camera.angle" not in p.plan.assumed


def test_empty_brief_raises_before_model_call():
    fake = FakeProvider()
    with pytest.raises(ValueError):
        run(propose(fake, "   "))
    assert fake.calls == []


def test_long_brief_is_truncated():
    fake = FakeProvider(FIGHT_ANSWER)
    run(propose(fake, "the hero fights the villain " + "x" * 5000))
    assert "x" * (MAX_BRIEF_CHARS + 1) not in fake.calls[0]


def test_invalid_planner_output_is_retried_with_problems():
    bad = {**FIGHT_ANSWER, "actors": [{**FIGHT_ANSWER["actors"][0], "side": "left"}, {**FIGHT_ANSWER["actors"][1], "side": "left"}]}
    fake = FakeProvider(bad, FIGHT_ANSWER)
    p = run(propose(fake, "the hero fights the villain"))
    assert len(fake.calls) == 2 and "opposite sides" in fake.calls[1]
    assert {a.side for a in p.plan.actors} == {"left", "right"}


def test_classify_scene_type_by_keyword_and_tie_is_none():
    assert classify_scene_type("a samurai duel at dusk") == "fight"
    assert classify_scene_type("a floating city above the clouds") == "concept_art"
    assert classify_scene_type("a child lost in a crowded market") is None  # emotion and concept art tie: the model decides
    assert classify_scene_type("something nice") is None


def test_apply_corrections_changes_the_plan_and_clears_assumed():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain")).plan
    out = apply_corrections(p, load_playbook("fight"), {"camera.angle": "high", "actors.villain.action_state": "falling"})
    assert out.camera.angle == "high" and out.actors[1].action_state == "falling"
    assert "camera.angle" not in out.assumed and "actors.villain.action_state" not in out.assumed


def test_apply_corrections_rejects_contradiction_and_leaves_plan_unchanged():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain")).plan
    before = p.model_dump()
    with pytest.raises(ValueError) as e:
        apply_corrections(p, load_playbook("fight"), {"actors.villain.side": "left"})
    assert "opposite sides" in str(e.value)
    assert p.model_dump() == before


def test_apply_corrections_rejects_unknown_path_and_bad_value():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain")).plan
    with pytest.raises(ValueError):
        apply_corrections(p, load_playbook("fight"), {"camera.colour": "red"})
    with pytest.raises(ValueError):
        apply_corrections(p, load_playbook("fight"), {"camera.angle": "sideways"})


def test_plan_to_words_mentions_every_actor_and_camera():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain")).plan
    words = plan_to_words(p)
    assert "hero" in words and "villain" in words and "striking" in words and "blocking" in words
    assert "low angle" in words and "behind" in words  # the playbook defaults
    assert "down-right" in words


def test_stated_action_state_is_not_asked_but_a_coincidental_word_is():
    # real-data finding: "lost her best friend" contains the state word "lost" but the plan's state is "grieving" - that must still be asked
    stated = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain, the hero striking hard"))
    assert "actors.hero.action_state" not in {q.field for q in stated.questions}
    assert "actors.villain.action_state" in {q.field for q in stated.questions}
    emo = {"actors": [{"id": "girl", "description": "teenage girl", "side": "center", "action_state": "grieving"}],
           "camera": {"angle": "eye_level", "distance": "close"}, "light": {"direction": "left"}}
    p = run(propose(FakeProvider(emo), "a girl who just lost her best friend"))
    assert "actors.girl.action_state" in {q.field for q in p.questions}


def test_prompt_tells_the_model_not_to_invent_people_or_use_the_word_slug():
    fake = FakeProvider({"actors": [], "camera": {"angle": "low", "distance": "wide"}, "light": {"direction": "top"}})
    p = run(propose(fake, "a floating city above the clouds"))
    assert p.plan.actors == []
    assert "only include people the brief" in fake.calls[0].lower()
    assert "slug" not in fake.calls[0].lower()


def test_prompt_asks_for_species_gender_age_and_visual_tags():
    fake = FakeProvider(FIGHT_ANSWER)
    run(propose(fake, "the hero fights the villain"))
    text = fake.calls[0].lower()
    assert "species" in text and "gender" in text and "age_group" in text and "visual tags" in text


def _solo(brief: str, **actor) -> "ScenePlan":
    answer = {"actors": [{"id": "hero", "description": "messy hair", "side": "center", "action_state": "grieving", **actor}],
              "camera": {"angle": "eye_level", "distance": "close"}, "light": {"direction": "left"}}
    return run(propose(FakeProvider(answer), brief, scene_type="emotion")).plan


def test_single_actor_gender_and_age_come_from_the_brief_words():
    # real-data finding: the model returned gender "neutral" for "a girl", and Qwen drew a boy
    girl = _solo("a girl who just lost her best friend").actors[0]
    assert (girl.gender, girl.age_group) == ("female", "teen")
    old = _solo("an old woman remembering her wedding day").actors[0]
    assert (old.gender, old.age_group) == ("female", "elder")
    assert _solo("a man and a woman waiting at a station", action_state="hopeful").actors[0].gender == "neutral"  # both genders named: ambiguous, left alone


def test_a_gender_the_model_chose_is_never_overridden():
    assert _solo("a girl who just lost her best friend", gender="male").actors[0].gender == "male"


def test_two_actor_plans_keep_neutral_gender():
    p = run(propose(FakeProvider(FIGHT_ANSWER), "the hero fights the villain")).plan
    assert {a.gender for a in p.actors} == {"neutral"}


class FlakyProvider(FakeProvider):
    """Raises like the real Ollama provider does when the model runs past its length budget, then answers."""

    def __init__(self, failures: int, *answers):
        super().__init__(*answers)
        self.failures = failures

    async def generate_structured(self, text, model, **kw):
        if self.failures:
            self.failures -= 1
            self.calls.append(text)
            raise RuntimeError("Model output reached its length limit (generated=1500, budget=1500)")
        return await super().generate_structured(text, model, **kw)


def test_a_model_that_runs_past_its_length_limit_is_retried_not_crashed():
    # real finding: GenerationLimitError escaped propose() and would have been an HTTP 500
    fake = FlakyProvider(1, FIGHT_ANSWER)
    p = run(propose(fake, "the hero fights the villain"))
    assert len(fake.calls) == 2 and "too long" in fake.calls[1].lower() and p.plan.actors


def test_a_model_that_never_answers_ends_as_value_error():
    with pytest.raises(ValueError, match="failed"):
        run(propose(FlakyProvider(99), "the hero fights the villain"))
