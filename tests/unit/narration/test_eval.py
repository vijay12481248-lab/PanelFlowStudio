import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, CritiqueReport, LineCheck, LineCritique, PanelFacts, Scene, ScriptIR, ScriptLine,
    SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import CompileResult
from engine.narration.eval import gold, metrics, report
from engine.narration.inputs import dump_chapter_inputs, load_chapter_inputs_from_dir
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.bible.store import BibleStore
from engine.narration.runtime.client import StepModelError
from engine.narration.steps.critique.judges import PairVerdict, Verdict
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


def _result(tmp_path, gate="pass"):
    ids = ("p1", "p2", "p3")
    script = ScriptIR(project_id="mini", lines=[
        ScriptLine(line_id=f"L{k}", panel_id=p, text={1: "line 1 <script>", 2: "Zed slams line 2 <script>", 3: "The line 3 <script>"}[k], facts_used=[], kind="narration",
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
    return CompileResult("r", gate, [], tmp_path, None, sheet, script, crit)


def _judge(pairs, grounded=lambda p: True):
    """Judge answers by prompt: pair prompts take the next queued verdict, grounded prompts use `grounded`."""
    pairs = list(pairs)

    def answer(prompt):
        if "Script A" in prompt:
            v = pairs.pop(0)
            if isinstance(v, Exception):
                raise v
            return v
        return Verdict(yes=grounded(prompt.rsplit("Line:", 1)[-1]), reason="why")

    return [answer] * 400


def _compiler(tmp_path, verdicts, grounded=lambda p: True, gate="pass", seen=None):
    async def run(inputs, workspace, facts_override=None, **kw):
        assert [f.panel_id for f in facts_override] == ["p1", "p2", "p3"]
        return _result(tmp_path, gate)

    return SimpleNamespace(run=run, client=FakeModelClient({"judge": _judge(verdicts, grounded)}), scheduler=_sched(),
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
    comp = _compiler(tmp_path, [_v("A"), _v("B")], grounded=lambda p: "line 2" not in p)  # compiler wins both orders
    rep = asyncio.run(metrics.run_eval(None, lambda bibles: comp))
    m = rep.chapters[0]
    assert m.slug == "mini"
    assert m.grounded == pytest.approx(2 / 3) and m.coverage == pytest.approx(2 / 3)
    assert m.pipeline_pass == pytest.approx(2 / 3) and m.gate == "pass"
    assert m.hallucinated_names == 1 and m.fallback_share == pytest.approx(1 / 3)  # Zed opens a sentence; The is a stopword
    assert m.preference == 1.0
    assert rep.totals.grounded == m.grounded and rep.totals.hallucinated_names == 1
    assert len(rep.spotcheck) == 3 and {s["line_id"] for s in rep.spotcheck} == {"L1", "L2", "L3"}
    assert all("action: " in s["facts"] for s in rep.spotcheck)


def test_preference_both_orders(root, tmp_path):
    comp = _compiler(tmp_path, [_v("A"), _v("A")])  # always picks the first slot: one win, one loss
    rep = asyncio.run(metrics.run_eval(["mini"], lambda bibles: comp))
    assert rep.chapters[0].preference == 0.5
    prompts = [c[1] for c in comp.client.calls if "Script A" in c[1]]
    assert len(prompts) == 2 and "Kai bolts." in prompts[0] and "line 1" in prompts[1]
    assert prompts[0].index("line 1") < prompts[0].index("Kai bolts.")
    assert prompts[1].index("Kai bolts.") < prompts[1].index("line 1")


def test_report_html_escapes_text(root, tmp_path):
    rep = asyncio.run(metrics.run_eval(None, lambda bibles: _compiler(tmp_path, [_v("B"), _v("B")], grounded=lambda p: "line 2" not in p)))
    j, h = report.write_report(rep, tmp_path / "out")
    html = h.read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'class="bad"' in html and j.name == "report.json"
    assert metrics.EvalReport.model_validate_json(j.read_text(encoding="utf-8")) == rep
    assert "equals 1 - fallback_share" in html and "<th>gate</th>" in html and "<th>panel facts</th>" in html


def test_compare_flags_regression():
    base = metrics.ChapterMetrics(slug="a", grounded=0.97, coverage=0.97, hallucinated_names=0,
                                  fallback_share=0.02, preference=0.6)
    same = base.model_copy()
    worse = base.model_copy(update={"grounded": 0.90, "hallucinated_names": 1, "preference": 0.5})
    mk = lambda c: metrics.EvalReport(created="t", chapters=[c], totals=c, spotcheck=[])
    assert metrics.compare(mk(same), mk(base)) == []
    out = metrics.compare(mk(worse), mk(base))
    assert len(out) == 6 and sum(s.startswith("a:") for s in out) == 3 and sum(s.startswith("ALL:") for s in out) == 3


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


def test_compare_flags_missing_slug_and_lost_preference():
    base = metrics.ChapterMetrics(slug="a", grounded=0.97, coverage=0.97, hallucinated_names=0,
                                  fallback_share=0.02, preference=0.6)
    gone = base.model_copy(update={"preference": None})
    mk = lambda *cs: metrics.EvalReport(created="t", chapters=list(cs), totals=cs[0], spotcheck=[])
    other = base.model_copy(update={"slug": "b"})
    out = metrics.compare(mk(gone), mk(base, other))
    assert "b: missing from the current run" in out and "a: preference went from 0.60 to None" in out
    assert "ALL: preference went from 0.60 to None" in out


def test_failed_gate_scores_worst_case_and_stays_in_totals(root, tmp_path):
    rep = asyncio.run(metrics.run_eval(None, lambda bibles: _compiler(tmp_path, [], gate="failed")))
    m = rep.chapters[0]
    assert m.gate == "failed" and (m.grounded, m.coverage, m.fallback_share, m.preference) == (0, 0, 1, None)
    assert rep.totals.fallback_share == 1 and rep.spotcheck == []
    assert 'class="bad">failed' in report.write_report(rep, tmp_path / "o")[1].read_text(encoding="utf-8")


def test_preference_windows_of_30_panels(tmp_path):
    ids = [f"q{k}" for k in range(70)]
    script = ScriptIR(project_id="m", lines=[ScriptLine(line_id=f"L{k}", panel_id=p, text=f"mine {k}", facts_used=[],
                                                        kind="narration") for k, p in enumerate(ids)])
    sheet = BeatSheet(project_id="m", hook="h", chapter_summary="s", scenes=[Scene(
        scene_id="s1", first_panel_id=ids[0], last_panel_id=ids[-1], goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="b1", panel_ids=ids, what_happens="w", function="setup", intensity=0.5)])])
    res = CompileResult("r", "pass", [], tmp_path, None, sheet, script, None)
    comp = _compiler(tmp_path, [_v("A")] * 6)
    pref = asyncio.run(metrics.preference(res, [{"panel_id": p, "text": f"theirs {p}"} for p in ids], comp))
    assert len(comp.client.calls) == 6 and pref == 0.5


def test_pair_failure_gives_none_preference_and_run_continues(root, tmp_path):
    shutil.copytree(MINI, root / "mini2")
    comp = _compiler(tmp_path, [StepModelError("judge", "boom"), _v("A"), _v("B")])
    rep = asyncio.run(metrics.run_eval(None, lambda bibles: comp))
    assert [c.preference for c in rep.chapters] == [None, 1.0]


def test_eval_gives_each_chapter_a_fresh_gold_bible(root, tmp_path):
    shutil.copytree(MINI, root / "mini2")
    seed = SeriesBible(series_key="mini-series", characters=[BibleCharacter(id="c1", name="Zed")], version=3)
    for slug in ("mini", "mini2"):
        (root / slug / "bible.json").write_text(seed.model_dump_json(), encoding="utf-8")
    stores = []

    def factory(bibles):
        stores.append(bibles)
        assert bibles.load("mini-series").version == 3  # not the previous chapter's saved copy
        bibles.save(bibles.load("mini-series"), "p", ["x"])
        return _compiler(tmp_path, [_v("A"), _v("B")])

    rep = asyncio.run(metrics.run_eval(None, factory))
    assert len(stores) == 2 and stores[0].root != stores[1].root
    assert [c.hallucinated_names for c in rep.chapters] == [0, 0]  # Zed is in the bible


def test_hallucinated_names_checks_sentence_starts():
    known = metrics._words(["Kai"]) | metrics._STOP
    assert metrics._invented_names("Zorg meets Kai. Then Mira's door. He runs", known) == 2


@pytest.mark.parametrize("slug", ["_work", "_reports", "Bad Slug", "a/b"])
def test_gold_slugs_are_validated(root, slug):
    with pytest.raises(ValueError, match="invalid series_key"):
        gold.add_gold("whatever", slug)
    with pytest.raises(ValueError, match="invalid series_key"):
        asyncio.run(metrics.run_eval([slug], lambda bibles: None))


def test_cli_gold_add_takes_kind(monkeypatch, capsys):
    from engine.narration import __main__ as cli

    seen = []
    monkeypatch.setattr(gold, "add_gold", lambda *a: seen.append(a) or "dest")
    assert cli.main(["gold", "add", "p1", "slug"]) == 0 and cli.main(["gold", "add", "p1", "s2", "--kind", "webtoon"]) == 0
    assert seen == [("p1", "slug", "manhwa"), ("p1", "s2", "webtoon")]
    with pytest.raises(SystemExit):
        cli.main(["gold", "add", "p1", "s3", "--kind", "comic"])


def test_cli_eval_rejects_bad_slug(root, monkeypatch, capsys):
    from engine.narration import __main__ as cli

    async def provider():
        return object()

    monkeypatch.setattr(cli, "_local_provider", provider)
    assert cli.main(["eval", "--slug", "_work"]) == 1
    assert "invalid series_key" in capsys.readouterr().out


def _gold_project(tmp_path, monkeypatch, segments):
    from engine.database.models import ScriptSegmentRecord, VideoScriptRecord
    from engine.database.session import SessionLocal
    from tests.unit.narration.test_inputs import _project

    pid, ids = _project(tmp_path, [(1, "DETECTED"), (2, "DETECTED")], title="Test - Chapter 1")
    run = tmp_path / "narration" / "run1"
    run.mkdir(parents=True)
    (run / "panel_facts.json").write_text('[{"panel_id": "x"}]', encoding="utf-8")
    with SessionLocal() as db:
        script = VideoScriptRecord(project_id=pid)
        db.add(script)
        db.flush()
        for seq, (typ, panel, text) in enumerate(segments, 1):
            db.add(ScriptSegmentRecord(script_id=script.id, project_id=pid, scene_id="s", sequence=seq, type=typ,
                                       text=text, source_evidence={"panel_ids": [ids[panel]]}))
        db.commit()
    monkeypatch.setattr(gold, "gold_root", lambda: tmp_path / "gold")
    store = BibleStore(tmp_path / "series")
    monkeypatch.setattr(gold, "BibleStore", lambda: store)
    return pid, ids, store


def test_add_gold_happy_path(tmp_path, monkeypatch):
    pid, ids, store = _gold_project(tmp_path, monkeypatch, [
        ("NARRATOR", 0, "Kai runs."), ("CHARACTER_DIALOGUE", 0, "Run!"), ("NARRATOR", 1, "The door slams.")])
    v1 = store.save(SeriesBible(series_key="test", characters=[BibleCharacter(id="c1", name="Kai")]), "older", ["a"])
    store.save(v1.model_copy(update={"plot_so_far": "this chapter"}), pid, ["update_plot"])
    dest = gold.add_gold(pid, "my-gold", "webtoon")
    ref = json.loads((dest / "reference.json").read_text(encoding="utf-8"))["lines"]
    assert ref == [{"panel_id": ids[0], "text": "Kai runs."}, {"panel_id": ids[1], "text": "The door slams."}]
    before = SeriesBible.model_validate_json((dest / "bible.json").read_text(encoding="utf-8"))
    assert before == v1 and before.plot_so_far == ""
    assert json.loads((dest / "meta.json").read_text(encoding="utf-8"))["kind"] == "webtoon"
    assert (dest / "inputs.json").exists() and (dest / "facts.json").exists()


def test_add_gold_empty_reference_warns_but_adds(tmp_path, monkeypatch, capsys):
    pid, _, _ = _gold_project(tmp_path, monkeypatch, [("CHARACTER_DIALOGUE", 0, "Run!")])
    dest = gold.add_gold(pid, "no-narration")
    assert "warning" in capsys.readouterr().out and dest.exists()
    assert json.loads((dest / "reference.json").read_text(encoding="utf-8")) == {"lines": []}


def test_add_gold_failure_removes_partial_slug(tmp_path, monkeypatch):
    pid, _, _ = _gold_project(tmp_path, monkeypatch, [("NARRATOR", 0, "Kai runs.")])
    real = gold._write

    def boom(path, payload):
        if path.name == "bible.json":
            raise OSError("disk full")
        real(path, payload)

    monkeypatch.setattr(gold, "_write", boom)
    with pytest.raises(OSError):
        gold.add_gold(pid, "half")
    assert not (tmp_path / "gold" / "half").exists()