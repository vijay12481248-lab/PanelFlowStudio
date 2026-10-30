import asyncio
import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, PanelFacts, Scene, ScriptIR, ScriptLine, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.critique.judges import Verdict, critique
from engine.narration.steps.repair import RepairDraft, fallback_text, repair_loop, with_successors
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader

BAD = "Bad line here now ok"


def _setup(n=3, action=None):
    facts = {f"p{k}": PanelFacts(panel_id=f"p{k}", order=k, is_story=True, shot="medium", characters_visible=["c1"],
                                 action=(action or f"Kai does thing {k}"), emotion="calm", importance=3,
                                 confidence=0.9) for k in range(1, n + 1)}
    lines = [ScriptLine(line_id=f"L{k:03d}", panel_id=f"p{k}", text=f"Kai walks on step {k} slowly", facts_used=["action"],
                        kind="narration") for k in range(1, n + 1)]
    sheet = BeatSheet(project_id="p", hook="h", chapter_summary="s", scenes=[Scene(
        scene_id="s0", first_panel_id="p1", last_panel_id=f"p{n}", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="b0", panel_ids=[f"p{k}" for k in range(1, n + 1)], what_happens="w", function="setup",
                    intensity=0.5)])])
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai")])
    return ScriptIR(project_id="p", lines=lines), facts, [f"p{k}" for k in range(1, n + 1)], sheet, bible


def _go(tmp_path, script, facts, ids, sheet, bible, judge, writer):
    client = FakeModelClient({"judge": [judge] * 500, "writer": list(writer)})
    cfg = lambda c: RoleConfig(model="m", temperature=0, max_tokens=64, concurrency=c)
    sched = ModelScheduler({"judge": cfg(2), "writer": cfg(1)}, RecordingUnloader())
    cache = ArtifactCache(tmp_path / "c")

    async def go():
        rep = await critique(script, facts, ids, sheet, bible, client, sched, cache)
        return await repair_loop(script, rep, facts, ids, sheet, bible, client, sched, cache)

    return asyncio.run(go()), client


def _bad_if(marker):
    return lambda p: Verdict(yes=marker not in p.rsplit("Line:", 1)[-1], reason="bad")


def _fix(text="Kai fixes the broken thing now"):
    return RepairDraft(text=text, facts_used=["action"])


def _broken(script, k, text=BAD):
    script.lines[k].text = text


def test_repair_fixes_line_in_one_round(tmp_path):
    script, *rest = _setup()
    _broken(script, 1)
    res, client = _go(tmp_path, script, *rest, _bad_if("Bad"), [_fix()])
    assert len(res.revisions) == 2 and res.gate == "pass" and res.reasons == []
    r1 = res.script
    assert r1.revision == 1 and r1.parent_revision == 0 and r1.changed_line_ids == ["L002"]
    assert [ln.status for ln in r1.lines] == ["passed", "repaired", "passed"]
    assert res.revisions[0].lines[1].text == BAD
    writer_prompt = [p for r, p, _ in client.calls if r == "writer"][0]
    assert BAD in writer_prompt and "step 1" in writer_prompt and "step 3" in writer_prompt


def test_two_rounds_then_fallback(tmp_path):
    script, *rest = _setup(n=10)
    _broken(script, 1)
    res, _ = _go(tmp_path, script, *rest, _bad_if("Bad"),
                 [_fix("Bad again fix one here"), _fix("Bad again fix two here")])
    assert [r.revision for r in res.revisions] == [0, 1, 2, 3]
    assert res.revisions[3].changed_line_ids == ["L002"]
    ln = res.script.lines[1]
    assert ln.status == "fallback" and ln.facts_used == ["action", "characters"] and ln.text == "Kai does thing 2."
    assert res.gate == "pass"  # 1 of 10


def test_fallback_hides_unknown_label():
    f = PanelFacts(panel_id="p1", order=1, is_story=True, shot="wide", characters_visible=["unknown_1"],
                   action="unknown_1 lunges at Kai", emotion="e", importance=3, confidence=0.9)
    assert fallback_text(f, {"c1": "Kai"}) == "A stranger lunges at Kai."
    long = f.model_copy(update={"action": " ".join(["word"] * 15)})
    assert fallback_text(long, {}) == "Word " + " ".join(["word"] * 11) + "."


def test_too_many_fallbacks_goes_to_review(tmp_path):
    for n_bad, gate in ((2, "review"), (1, "pass")):
        script, *rest = _setup(n=10)
        for k in range(n_bad):
            _broken(script, k, f"{BAD} {k}")
        res, _ = _go(tmp_path / gate, script, *rest, _bad_if("Bad"), [_fix(f"{BAD} fix {i}") for i in range(4)])
        assert res.gate == gate
        if gate == "review":
            assert res.reasons == ["2 of 10 lines fell back to facts"]


def test_repair_rejudges_only_changed_lines_and_their_successors(tmp_path):
    script, *rest = _setup(n=5)
    _broken(script, 1)
    res, client = _go(tmp_path, script, *rest, _bad_if("Bad"), [_fix()])
    assert res.gate == "pass"
    judge = [p for r, p, _ in client.calls if r == "judge"]
    assert len(judge) == 5 * 4 + 4 + 2  # full critique; L002 anew; L003 clear+flow (new previous line), grounded+voice cached


def test_with_successors():
    script, *_ = _setup(n=4)
    assert with_successors(script, ["L002", "L004"]) == ["L002", "L003", "L004"]



def test_short_fallback_is_not_blocked_by_word_budget(tmp_path):
    script, *rest = _setup(n=10, action="A man stands")
    _broken(script, 1)
    res, _ = _go(tmp_path, script, *rest, _bad_if("Bad"), [_fix("Bad again fix one here"), _fix("Bad again fix two here")])
    assert res.script.lines[1].text == "A man stands." and res.script.lines[1].status == "fallback"
    assert res.gate == "pass" and not any(lc.blocked for lc in res.report.lines)


def test_fallback_that_breaks_a_rule_goes_to_review(tmp_path):
    script, *rest = _setup(n=10, action="Kai meets Zorg there now")
    _broken(script, 1)
    res, _ = _go(tmp_path, script, *rest, _bad_if("Bad"), [_fix("Bad again fix one here"), _fix("Bad again fix two here")])
    assert res.script.lines[1].status == "fallback"
    assert res.gate == "review" and res.reasons == ["1 fallback lines still break rules"]
    assert [lc.line_id for lc in res.report.lines if lc.blocked] == ["L002"]