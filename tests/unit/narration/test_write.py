import asyncio
import re

import pytest

from engine.narration.artifacts import Beat, BeatSheet, BibleCharacter, PanelFacts, Scene, SeriesBible
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.client import StepModelError
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.understand import NeedsReview
from engine.narration.steps.write import CandidatesDraft, LineDraft, SceneLinesDraft, write_chapter
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader


def _facts(k, is_story=True):
    return PanelFacts(panel_id=f"p{k}", order=k, is_story=is_story, shot="medium", action=f"act {k}",
                      emotion="calm", importance=3, confidence=0.9, characters_visible=["unknown_1"])


def _sheet(*ranges):
    scenes = [Scene(scene_id=f"s{i}", first_panel_id=a, last_panel_id=b, goal="g", conflict="c", turn=f"turn {i}",
                    beats=[Beat(beat_id=f"s{i}b0", panel_ids=[a, b], what_happens="w", function="setup", intensity=0.5)])
              for i, (a, b) in enumerate(ranges)]
    return BeatSheet(project_id="proj", scenes=scenes, hook="a dark hook", chapter_summary="sum")


def _bible():
    return SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai")])


def _draft(prompt, skip=(), tag="x", facts=("action",)):
    ks = [int(m) for m in re.findall(r"^P(\d+) \|", prompt, re.M) if int(m) not in skip]
    return SceneLinesDraft(lines=[LineDraft(panel=k, text=f"{tag} line for P{k} goes right here", facts_used=list(facts),
                                            kind="narration") for k in ks])


def _cands(prompt):
    return CandidatesDraft(candidates=["one two three four five", "six seven eight nine ten", "a b c d e"])


def _answer(prompt):
    return _cands(prompt) if "exactly 3 candidates" in prompt else _draft(prompt)


def _run(tmp_path, facts, sheet, responses, client=None):
    client = client or FakeModelClient({"writer": responses})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    out = asyncio.run(write_chapter("proj", facts, sheet, _bible(), client, sched, ArtifactCache(tmp_path / "c")))
    return out, client


def test_one_line_per_story_panel_in_order(tmp_path):
    facts = [_facts(k, is_story=k != 6) for k in range(1, 9)]
    (script, cands), client = _run(tmp_path, facts, _sheet(("p1", "p3"), ("p4", "p8")), [_answer] * 4)
    assert [ln.panel_id for ln in script.lines] == ["p1", "p2", "p3", "p4", "p5", "p7", "p8"]
    assert [ln.line_id for ln in script.lines] == [f"L{k:03d}" for k in range(1, 8)]
    for ln, local in zip(script.lines, [1, 2, 3, 1, 2, 3, 4]):
        assert f"line for P{local} " in ln.text
    assert "beat:s1b0 P1-P4:" in client.calls[1][1]
    assert [ln.kind for ln in script.lines] == ["hook"] + ["narration"] * 5 + ["cliffhanger"]
    assert {ln.status for ln in script.lines} == {"draft"} and script.revision == 0
    assert "stranger" in client.calls[0][1] and "unknown_1" not in client.calls[0][1]


def test_scene_over_30_panels_is_chunked(tmp_path):
    n, seq = 65, iter(range(10))
    facts = [_facts(k) for k in range(1, n + 1)]
    answer = lambda p: _cands(p) if "exactly 3 candidates" in p else _draft(p, tag=f"c{next(seq)}")
    (script, _), client = _run(tmp_path, facts, _sheet(("p1", f"p{n}")), [answer] * 5)
    scene_calls = [c[1] for c in client.calls if "exactly 3 candidates" not in c[1]]
    assert len(scene_calls) == 3 and len(script.lines) == n
    assert all(f"c0 line for P{k} " in scene_calls[1] for k in (28, 29, 30))
    assert "c0 line for P27 " not in scene_calls[1]
    assert "c0 line for P" not in scene_calls[0]
    assert script.lines[29].text.startswith("c0 ") and script.lines[30].text.startswith("c1 ")


def test_missing_panel_reasks_once_then_review(tmp_path):
    facts = [_facts(k) for k in range(1, 4)]
    bad = lambda p: _draft(p, skip=(2,))
    with pytest.raises(NeedsReview, match="count mismatch") as e:
        _run(tmp_path, facts, _sheet(("p1", "p3")), [bad, bad, _cands, _cands])
    assert "P2" in str(e.value)


def test_reask_fixes_answer(tmp_path):
    facts = [_facts(k) for k in range(1, 4)]
    (script, _), client = _run(tmp_path, facts, _sheet(("p1", "p3")),
                               [lambda p: _draft(p, skip=(2,)), _answer, _answer, _answer])
    scene_calls = [c[1] for c in client.calls if "exactly 3 candidates" not in c[1]]
    assert len(scene_calls) == 2 and "Fix these problems" in scene_calls[1]
    assert len(script.lines) == 3


def test_candidates_three_each(tmp_path):
    (_, cands), _ = _run(tmp_path, [_facts(1), _facts(2)], _sheet(("p1", "p2")), [_answer] * 3)
    assert set(cands) == {"hook", "cliffhanger"} and all(len(v) == 3 for v in cands.values())


def test_rerun_uses_cache(tmp_path):
    facts = [_facts(k) for k in range(1, 4)]
    first, _ = _run(tmp_path, facts, _sheet(("p1", "p3")), [lambda p: _draft(p, skip=(2,)), _answer, _answer, _answer])
    second, client = _run(tmp_path, facts, _sheet(("p1", "p3")), [])
    assert client.calls == [] and second == first


def test_prompt_over_budget_fails_loud(tmp_path):
    client = FakeModelClient({"writer": [_answer] * 3}, params={"num_ctx": 300, "max_tokens": 200})
    with pytest.raises(StepModelError, match="writer"):
        _run(tmp_path, [_facts(1)], _sheet(("p1", "p1")), [], client=client)
    assert client.calls == []


@pytest.mark.parametrize("bad", ["beat:nope", "foo"])
def test_bad_facts_used_reasks_once(tmp_path, bad):
    facts = [_facts(k) for k in range(1, 4)]
    (script, _), client = _run(tmp_path, facts, _sheet(("p1", "p3")),
                               [lambda p: _draft(p, facts=("action", bad)), _answer, _answer, _answer])
    scene_calls = [c[1] for c in client.calls if "exactly 3 candidates" not in c[1]]
    assert len(scene_calls) == 2 and "facts_used" in scene_calls[1]
    assert all(ln.facts_used == ["action"] for ln in script.lines)


def test_overlapping_scenes_raise(tmp_path):
    facts = [_facts(k) for k in range(1, 5)]
    with pytest.raises(ValueError, match="overlap"):
        _run(tmp_path, facts, _sheet(("p1", "p3"), ("p2", "p4")), [_answer] * 4)