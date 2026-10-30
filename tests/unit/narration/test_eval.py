import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, CritiqueReport, LineCheck, LineCritique, PanelFacts, Scene, ScriptIR, ScriptLine,
)
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import CompileResult
from engine.narration.eval import gold, metrics, report
from engine.narration.inputs import dump_chapter_inputs, load_chapter_inputs_from_dir
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.critique.judges import PairVerdict
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader, make_chapter_inputs

MINI = Path(__file__).resolve().parents[2] / "fixtures" / "narration_gold_mini"


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "gold"
    monkeypatch.setattr(gold, "gold_root", lambda: r)
    shutil.copytree(MINI, r / "mini")
    return r


def _sched():
    roles = {"judge": RoleConfig(model="m", temperature=0, max_tokens=64, concurrency=1)}
    return ModelScheduler(roles, RecordingUnloader())


def _result(tmp_path):
    ids = ("p1", "p2", "p3")
    script = ScriptIR(project_id="mini", lines=[
        ScriptLine(line_id=f"L{k}", panel_id=p, text=f"line {k} <script>", facts_used=[], kind="narration",
                   status="fallback" if k == 3 else "passed") for k, p in enumerate(ids, 1)])
    ok = {1: True, 2: False, 3: True}
    lines = [LineCritique(line_id=f"L{k}", checks=[
        LineCheck(rule="grounded", passed=ok[k], severity="block", reason="r"),
        LineCheck(rule="unknown_name", passed=k != 2, severity="block", reason="Zed" if k == 2 else "")])
        for k in (1, 2, 3)]
    crit = CritiqueReport(revision=0, lines=lines, coverage=2 / 3, pace_estimate=1, repetition=0, gate="pass")
    sheet = BeatSheet(project_id="mini", hook="h", chapter_summary="s", scenes=[Scene(
        scene_id="s1", first_panel_id="p1", last_panel_id="p3", goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="b1", panel_ids=list(ids), what_happens="w", function="setup", intensity=0.5)])])
    return CompileResult("r", "pass", [], tmp_path, None, sheet, script, crit)


def _compiler(tmp_path, verdicts):
    async def run(inputs, workspace, facts_override=None, **kw):
        assert [f.panel_id for f in facts_override] == ["p1", "p2", "p3"]
        return _result(tmp_path)

    return SimpleNamespace(run=run, client=FakeModelClient({"judge": verdicts}), scheduler=_sched(),
                           cache=ArtifactCache(tmp_path / "cache"))


def _v(w):
    return PairVerdict(winner=w, reason="x")


def test_dump_and_load_inputs_round_trip(tmp_path):
    src = make_chapter_inputs(tmp_path, 2, {1: ["Hi", "There"]})
    dump_chapter_inputs(src, tmp_path / "g")
    back = load_chapter_inputs_from_dir(tmp_path / "g")
    assert [p.panel_id for p in back.panels] == ["p1", "p2"]
    assert back.panels[0].ocr == src.panels[0].ocr and back.series_key == "test-series"
    assert back.panels[1].image_path.parent == tmp_path / "g" / "panels" and back.panels[1].image_path.exists()


def test_eval_metrics_on_mini_fixture(root, tmp_path):
    comp = _compiler(tmp_path, [_v("A"), _v("B")])  # compiler wins both orders
    rep = asyncio.run(metrics.run_eval(None, lambda: comp))
    m = rep.chapters[0]
    assert m.slug == "mini"
    assert m.grounded == pytest.approx(2 / 3) and m.coverage == pytest.approx(2 / 3)
    assert m.hallucinated_names == 1 and m.fallback_share == pytest.approx(1 / 3)
    assert m.preference == 1.0
    assert rep.totals.grounded == m.grounded and rep.totals.hallucinated_names == 1
    assert len(rep.spotcheck) == 3 and {s["line_id"] for s in rep.spotcheck} == {"L1", "L2", "L3"}


def test_preference_both_orders(root, tmp_path):
    comp = _compiler(tmp_path, [_v("A"), _v("A")])  # always picks the first slot: one win, one loss
    rep = asyncio.run(metrics.run_eval(["mini"], lambda: comp))
    assert rep.chapters[0].preference == 0.5
    prompts = [c[1] for c in comp.client.calls]
    assert len(prompts) == 2 and "Kai bolts." in prompts[0] and "line 1" in prompts[1]
    assert prompts[0].index("line 1") < prompts[0].index("Kai bolts.")
    assert prompts[1].index("Kai bolts.") < prompts[1].index("line 1")


def test_report_html_escapes_text(root, tmp_path):
    rep = asyncio.run(metrics.run_eval(None, lambda: _compiler(tmp_path, [_v("B"), _v("B")])))
    j, h = report.write_report(rep, tmp_path / "out")
    html = h.read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'class="bad"' in html and j.name == "report.json"
    assert metrics.EvalReport.model_validate_json(j.read_text(encoding="utf-8")) == rep


def test_compare_flags_regression():
    base = metrics.ChapterMetrics(slug="a", grounded=0.97, coverage=0.97, hallucinated_names=0,
                                  fallback_share=0.02, preference=0.6)
    same = base.model_copy()
    worse = base.model_copy(update={"grounded": 0.90, "hallucinated_names": 1, "preference": 0.5})
    mk = lambda c: metrics.EvalReport(created="t", chapters=[c], totals=c, spotcheck=[])
    assert metrics.compare(mk(same), mk(base)) == []
    out = metrics.compare(mk(worse), mk(base))
    assert len(out) == 3 and all(s.startswith("a:") for s in out)


def test_add_gold_refuses_existing_slug(root):
    with pytest.raises(FileExistsError):
        gold.add_gold("whatever", "mini")


def test_cli_eval_exits_2_on_regression(root, tmp_path, monkeypatch, capsys):
    from engine.narration import __main__ as cli

    good = metrics.ChapterMetrics(slug="a", grounded=0.97, coverage=0.97, hallucinated_names=0, fallback_share=0)
    bad = good.model_copy(update={"grounded": 0.5})
    mk = lambda c: metrics.EvalReport(created="t", chapters=[c], totals=c, spotcheck=[])

    async def fake_run(slugs, factory):
        return mk(bad)

    async def provider():
        return object()

    base = tmp_path / "base.json"
    base.write_text(mk(good).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(metrics, "run_eval", fake_run)
    monkeypatch.setattr(cli, "_local_provider", provider)
    assert cli.main(["eval", "--baseline", str(base), "--out", str(tmp_path / "o")]) == 2
    assert "regression: a: grounded" in capsys.readouterr().out
