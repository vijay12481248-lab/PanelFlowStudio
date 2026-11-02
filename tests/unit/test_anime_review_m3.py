import asyncio

import pytest

from engine.anime.review import script
from engine.anime.review.models import Beat, Clip, ClipPlan, Understanding

PLAN = ClipPlan(clips=[Clip(id="c01", beat_id="b01", start=0, end=5, purpose="x"),
                       Clip(id="c02", beat_id="b02", start=9, end=14, purpose="y")], total_sec=10, budget_sec=20)
U = Understanding(summary="s", characters=["A"], beats=[
    Beat(id="b01", start=0, end=5, kind="opening", label="x", why="w"),
    Beat(id="b02", start=9, end=14, kind="highlight", label="y", why="w")])
WORDS = " ".join(["word"] * 15)


def S(clip, role, text=WORDS):
    return script._SegOut(clip_id=clip, role=role, text=text)


def good(**kw):
    segs = [S("c01", "hook"), S("c01", "recap"), S("c02", "critique"), S("c02", "verdict"), S("c02", "cta")]
    return script._ScriptOut(title_hook="t", rating=kw.get("rating", 7.5), segments=kw.get("segments", segs))


def test_valid_script_passes():
    assert script.validate(good(), PLAN) == []


def test_validation_catches_problems():
    bad = good(segments=[S("c09", "recap", "too short"), S("c01", "verdict", "Let's delve into it " + WORDS)], rating=11)
    msgs = " | ".join(script.validate(bad, PLAN))
    for needle in ("first segment", "last segment", "critique", "unknown clip_id", "words", "stock phrases", "rating", "never narrated"):
        assert needle in msgs


def test_retries_with_feedback_then_succeeds():
    calls = []

    class P:
        async def generate_structured(self, prompt, model, **kw):
            calls.append(prompt)
            return good(rating=99) if len(calls) == 1 else good()
    sc = asyncio.run(script.write_script("T", U, PLAN, P()))
    assert len(calls) == 2 and "rating must be" in calls[1] and sc.segments[0].id == "s1"


def test_gives_up_after_retries():
    class P:
        async def generate_structured(self, prompt, model, **kw):
            return good(rating=99)
    with pytest.raises(ValueError, match="failed validation"):
        asyncio.run(script.write_script("T", U, PLAN, P(), max_attempts=2))


def test_funny_segment_refused_without_funny_beat():
    segs = [S("c01", "hook"), S("c02", "funny"), S("c01", "critique"), S("c02", "verdict"), S("c02", "cta")]
    assert any("funny" in m for m in script.validate(good(segments=segs), PLAN, has_funny=False))
