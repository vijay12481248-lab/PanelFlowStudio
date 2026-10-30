import asyncio
import re

import pytest

from engine.narration.artifacts import Beat, BeatSheet, PanelFacts, Scene, ScriptIR, ScriptLine, SeriesBible
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.perform import MarksDraft, SceneMarksDraft, marks_to_tts, perform
from engine.narration.steps.understand import NeedsReview
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader


@pytest.mark.parametrize("energy,beat,scene_last,last,nxt,want", [
    ("med", "setup", False, False, False, (0.95, 250)),
    ("high", "setup", False, False, False, (1.0, 250)),
    ("med", "escalate", False, False, False, (1.0, 250)),
    ("med", "payoff", True, False, False, (1.0, 650)),
    ("low", "setup", False, False, False, (0.9, 250)),
    ("med", "reveal", False, False, True, (0.9, 650)),
    ("high", "reveal", False, False, False, (0.9, 250)),
    ("med", "setup", False, False, True, (0.95, 650)),
    ("high", "cliffhanger", True, True, False, (1.0, 0)),
])
def test_marks_map_to_rate_and_pause(energy, beat, scene_last, last, nxt, want):
    d = MarksDraft(line=1, emotion="x", energy=energy)
    assert marks_to_tts(d, beat, scene_last, last, next_is_reveal=nxt) == want


def _facts(k):
    return PanelFacts(panel_id=f"p{k}", order=k, is_story=True, shot="medium", action=f"act {k}",
                      emotion="calm", importance=3, confidence=0.9)


def _sheet():
    def sc(i, a, b, fn):
        return Scene(scene_id=f"s{i}", first_panel_id=f"p{a}", last_panel_id=f"p{b}", goal="g", conflict="c", turn="t",
                     beats=[Beat(beat_id=f"b{i}", panel_ids=[f"p{k}" for k in range(a, b + 1)], what_happens="w",
                                 function=fn, intensity=0.5)])
    return BeatSheet(project_id="proj", scenes=[sc(0, 1, 2, "setup"), sc(1, 3, 4, "reveal")], hook="h", chapter_summary="s")


def _script():
    return ScriptIR(project_id="proj", revision=2, lines=[
        ScriptLine(line_id=f"L{k}", panel_id=f"p{k}", text=f"Kai draws the sword now {k}", facts_used=[], kind="narration")
        for k in range(1, 5)])


def _answer(prompt, skip=(), emph=("sword",), energy="med"):
    ks = [int(m) for m in re.findall(r"^P(\d+) \|", prompt, re.M) if int(m) not in skip]
    return SceneMarksDraft(lines=[MarksDraft(line=k, emotion="tense", energy=energy, emphasis_words=list(emph)) for k in ks])


def _run(tmp_path, responses, client=None):
    client = client or FakeModelClient({"writer": responses})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    plan = asyncio.run(perform(_script(), _sheet(), [_facts(k) for k in range(1, 5)], SeriesBible(series_key="s"),
                               client, sched, ArtifactCache(tmp_path / "c")))
    return plan, client


def test_one_mark_per_line_in_order(tmp_path):
    plan, client = _run(tmp_path, [_answer] * 2)
    assert [m.line_id for m in plan.lines] == ["L1", "L2", "L3", "L4"] and plan.script_revision == 2
    assert len(client.calls) == 2 and "P2 | Kai draws the sword now 2" in client.calls[0][1]
    # L2 ends its scene; L3 precedes a reveal line; L4 is the chapter's last (floor 150)
    assert [m.pause_after_ms for m in plan.lines] == [250, 650, 650, 150]
    assert [m.rate for m in plan.lines] == [0.95, 0.95, 0.9, 0.9]


def test_bad_structure_reasks_then_review(tmp_path):
    plan, client = _run(tmp_path, [lambda p: _answer(p, skip=(2,)), _answer, _answer])
    assert len(plan.lines) == 4 and len(client.calls) == 3 and "Fix these problems" in client.calls[1][1]
    bad = lambda p: _answer(p, skip=(2,))
    with pytest.raises(NeedsReview, match="P1..P2"):
        _run(tmp_path / "x", [bad, bad, _answer, _answer])


def test_emphasis_words_filtered_to_line(tmp_path):
    plan, _ = _run(tmp_path, [lambda p: _answer(p, emph=("Sword", "dragon", "swo"))] * 2)
    assert plan.lines[0].emphasis_words == ["Sword"]


def test_rerun_zero_calls(tmp_path):
    first, _ = _run(tmp_path, [_answer] * 2)
    second, client = _run(tmp_path, [])
    assert client.calls == [] and second == first


def test_emphasis_punctuation_trimmed(tmp_path):
    plan, _ = _run(tmp_path, [lambda p: _answer(p, emph=("sword.", "Kai,", "sword"))] * 2)
    assert plan.lines[0].emphasis_words == ["sword", "Kai"]


def test_stray_line_joins_scene_before_it(tmp_path):
    sheet = _sheet()
    sheet.scenes[1].last_panel_id = "p3"  # p4 is now in no scene
    client = FakeModelClient({"writer": [_answer] * 2})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    plan = asyncio.run(perform(_script(), sheet, [_facts(k) for k in range(1, 5)], SeriesBible(series_key="s"),
                               client, ModelScheduler({"writer": role}, RecordingUnloader()), ArtifactCache(tmp_path / "c")))
    assert len(plan.lines) == 4 and len(client.calls) == 2
    assert "P2 | Kai draws the sword now 4" in client.calls[1][1]
