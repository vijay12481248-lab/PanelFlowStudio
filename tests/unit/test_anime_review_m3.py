import asyncio

import pytest

from engine.anime.review import script
from engine.anime.review.models import Beat, Clip, ClipPlan, Understanding

PLAN = ClipPlan(clips=[Clip(id="c01", beat_id="b01", start=0, end=5, purpose="x"),
                       Clip(id="c02", beat_id="b02", start=9, end=14, purpose="y"),
                       Clip(id="c03", beat_id="b03", start=30, end=35, purpose="z")], total_sec=15, budget_sec=20)
U = Understanding(summary="s", characters=["A"], beats=[
    Beat(id="b01", start=0, end=5, kind="opening", label="x", why="w"),
    Beat(id="b02", start=9, end=14, kind="highlight", label="y", why="w", visual="A runs"),
    Beat(id="b03", start=30, end=35, kind="ending", label="z", why="w")])
W = " ".join(["word"] * 20)


class FakeLLM:
    """Answers each section's schema; records prompts so tests can inspect them."""

    def __init__(self, bad_first=None):
        self.prompts, self.bad_first, self.calls = [], bad_first, 0

    async def generate_structured(self, prompt, model, **kw):
        self.prompts.append(prompt)
        self.calls += 1
        if model is script._Intro:
            return model(hook="Hook line right here now.", recap=[W, W])
        if model is script._Verdict:
            return model(title_hook="Title", rating=8.0, verdict=W + " eight out of ten", cta=W)
        if self.bad_first and self.calls == 2:
            return model(segments=["too short"])  # first section call is bad once
        return model(segments=[W, W])


def run(llm, **kw):
    return asyncio.run(script.write_script("T", U, PLAN, llm, **kw))


def test_structure_order_and_binding():
    sc = run(FakeLLM(), target_sec=120)
    roles = [s.role for s in sc.segments]
    assert roles[0] == "hook" and roles[-2:] == ["verdict", "cta"] and "critique" in roles
    assert {s.clip_id for s in sc.segments} == {"c01", "c02", "c03"}  # every clip narrated
    assert [s.id for s in sc.segments] == [f"s{i}" for i in range(1, len(sc.segments) + 1)]
    blocks = [s.clip_id for s in sc.segments if s.role in ("highlight", "recap") and s.clip_id]
    assert sc.rating == 8.0 and sc.title_hook == "Title"


def test_length_scales_with_target():
    short = sum(len(s.text.split()) for s in run(FakeLLM(), target_sec=60).segments)
    long_ = sum(len(s.text.split()) for s in run(FakeLLM(), target_sec=400).segments)
    assert long_ > short  # more paragraphs requested per clip


def test_visual_and_dialogue_reach_the_prompt():
    llm = FakeLLM()
    run(llm, target_sec=60)
    assert any("On screen: A runs" in p for p in llm.prompts)


def test_bad_section_is_retried_with_feedback():
    llm = FakeLLM(bad_first=True)
    run(llm, target_sec=60)
    assert any("Fix these problems" in p and "words" in p for p in llm.prompts)


def test_ai_isms_and_short_text_flagged():
    assert script.problems(["Let's delve into this " + W]) and script.problems(["too short"])
    assert script.problems([W]) == []


def test_gives_up_after_retries():
    class Bad(FakeLLM):
        async def generate_structured(self, prompt, model, **kw):
            return script._Lines(segments=["nope"]) if model is script._Lines else await super().generate_structured(prompt, model)
    with pytest.raises(ValueError, match="failed validation"):
        run(Bad(), target_sec=60)


def test_empty_plan_refused():
    with pytest.raises(ValueError):
        asyncio.run(script.write_script("T", U, ClipPlan(clips=[], total_sec=0, budget_sec=0), FakeLLM()))
