import asyncio

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, CritiqueReport, PanelFacts, Scene, ScriptIR, ScriptLine, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.critique.judges import PairVerdict, Verdict, critique, pick_best
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader

TEXTS = ["Kai strikes the gate hard now", "Kai breaks through and runs away", "Rain falls over the quiet city"]


def _setup(n=3):
    facts = {f"p{k}": PanelFacts(panel_id=f"p{k}", order=k, is_story=True, shot="medium", action=f"unique action {k}",
                                 emotion="calm", importance=3, confidence=0.9) for k in range(1, n + 1)}
    lines = [ScriptLine(line_id=f"L{k:03d}", panel_id=f"p{k}", text=TEXTS[k - 1], facts_used=[], kind="narration")
             for k in range(1, n + 1)]
    sheet = BeatSheet(project_id="p", hook="h", chapter_summary="s", scenes=[Scene(
        scene_id="s0", first_panel_id="p1", last_panel_id=f"p{n}", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id=f"b{k}", panel_ids=[f"p{k}"], what_happens=f"beat text {k}", function="setup",
                    intensity=0.5) for k in range(1, n + 1)])])
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai")])
    return ScriptIR(project_id="p", lines=lines), facts, [f"p{k}" for k in range(1, n + 1)], sheet, bible


def _run(tmp_path, answer, fn, n_calls=None):
    client = FakeModelClient({"judge": [answer] * 100})
    sched = ModelScheduler({"judge": RoleConfig(model="j", temperature=0, max_tokens=64, concurrency=2)},
                           RecordingUnloader())
    cache = ArtifactCache(tmp_path / "c")
    return asyncio.run(fn(client, sched, cache)), client


def _yes(prompt):
    return Verdict(yes=True, reason="ok")


def test_judge_sees_only_its_inputs(tmp_path):
    script, facts, ids, sheet, bible = _setup()
    _, client = _run(tmp_path, _yes, lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca, line_ids=["L002"]))
    prompts = [p for _, p, _ in client.calls]
    grounded = [p for p in prompts if "unique action 2" in p]
    assert len(grounded) == 1 and "beat text 2" in grounded[0] and TEXTS[1] in grounded[0]
    assert all("unique action 1" not in p and "unique action 3" not in p and "beat text 1" not in p for p in prompts)
    clear = [p for p in prompts if TEXTS[0] in p and TEXTS[1] in p]
    assert len(clear) == 2 and all("unique action" not in p for p in clear)  # clear + flow
    assert all(TEXTS[2] not in p for p in prompts)


def test_pairwise_runs_both_orders(tmp_path):
    cands = ["first one", "second one", "third one"]
    best, client = _run(tmp_path, lambda p: PairVerdict(winner="A", reason="x"),
                        lambda c, s, ca: pick_best("hook", cands, "ctx", c, s, ca))
    assert len(client.calls) == 6 and best == "first one"
    best, _ = _run(tmp_path / "b", lambda p: PairVerdict(winner="B" if "second one" in p.split("Option B")[1] else "A", reason="x"),
                   lambda c, s, ca: pick_best("hook", cands, "ctx", c, s, ca))
    assert best == "second one"


def test_gate_repair_when_any_block_fails(tmp_path):
    script, facts, ids, sheet, bible = _setup()
    rep, _ = _run(tmp_path, _yes, lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca))
    assert rep.gate == "pass" and rep.coverage == 1.0 and rep.lines[0].scores == dict(grounded=True, clear=True, voice=True, flow=True)
    no = lambda p: Verdict(yes="Rain falls" not in p, reason="bad")
    rep, _ = _run(tmp_path / "b", no, lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca))
    assert rep.gate == "repair" and [ln.blocked for ln in rep.lines] == [False, False, True]


def test_coverage_excludes_fallback_lines(tmp_path):
    script, facts, ids, sheet, bible = _setup()
    script.lines[1].status = "fallback"
    rep, _ = _run(tmp_path, _yes, lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca))
    assert rep.coverage == 2 / 3


def test_rejudge_only_changed_lines(tmp_path):
    script, facts, ids, sheet, bible = _setup()
    prev, _ = _run(tmp_path, lambda p: Verdict(yes="Rain falls" not in p, reason="bad"),
                   lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca))
    assert isinstance(prev, CritiqueReport)
    rep, client = _run(tmp_path / "b", _yes, lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca,
                                                                        line_ids=["L002"], previous=prev))
    assert len(client.calls) == 4
    assert rep.lines[2].checks == prev.lines[2].checks and rep.lines[2].blocked
    assert rep.gate == "repair"


def test_judge_cache_rerun_zero_calls(tmp_path):
    script, facts, ids, sheet, bible = _setup()
    run = lambda c, s, ca: critique(script, facts, ids, sheet, bible, c, s, ca)
    first, c1 = _run(tmp_path, _yes, run)
    second, c2 = _run(tmp_path, _yes, run)
    assert len(c1.calls) == 12 and len(c2.calls) == 0 and second == first