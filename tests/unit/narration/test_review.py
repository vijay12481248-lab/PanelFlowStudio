import asyncio
import json

import pytest

from engine.narration import review
from engine.narration.artifacts import ScriptIR
from engine.narration.bible.store import BibleStore
from engine.narration.cache import ArtifactCache
from engine.narration.review import ReviewItem
from engine.narration.steps.repair import RepairDraft
from tests.unit.narration.test_compiler import _compiler, _go, _write_responses


def _parked(tmp_path):
    comp = _compiler(tmp_path, _write_responses(bad="number 2"))
    result = _go(tmp_path, comp, stop_after="write")
    assert result.gate == "review"
    return comp, result


def _script(run_dir) -> ScriptIR:
    return ScriptIR.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))


def test_review_json_written_on_review_gate(tmp_path):
    _, res = _parked(tmp_path)
    item = ReviewItem.model_validate_json((res.run_dir / "review.json").read_text(encoding="utf-8"))
    assert item.status == "pending" and item.project_id == "proj-test" and item.run_dir == str(res.run_dir)
    assert item.line_ids == ["L002"] and item.reasons == res.reasons


def test_review_json_absent_on_pass(tmp_path):
    res = _go(tmp_path, _compiler(tmp_path, _write_responses()), stop_after="write")
    assert res.gate == "pass" and not (res.run_dir / "review.json").exists()


def test_list_pending_skips_approved(tmp_path):
    comp, res = _parked(tmp_path)
    assert [i.run_id for i in review.list_pending(tmp_path)] == [res.run_id]
    review.approve(res.run_dir, comp.bibles)
    assert review.list_pending(tmp_path) == []


def test_edit_line_rejects_banned_phrase(tmp_path):
    comp, res = _parked(tmp_path)
    with pytest.raises(ValueError, match="banned_phrase"):
        review.edit_line(res.run_dir, "L002", "In this panel the man stands", comp.bibles)
    assert not (res.run_dir / "script_r5.json").exists()


def test_edit_creates_new_revision_with_lineage(tmp_path):
    comp, res = _parked(tmp_path)
    before = res.script
    out = review.edit_line(res.run_dir, "L002", "He walks through the quiet hall slowly", comp.bibles)
    assert out.revision == before.revision + 1 and out.parent_revision == before.revision
    assert out.changed_line_ids == ["L002"]
    ln = out.lines[1]
    assert ln.status == "passed" and ln.facts_used == before.lines[1].facts_used
    assert (res.run_dir / f"script_r{out.revision}.json").exists() and _script(res.run_dir).revision == out.revision
    assert review.accept_line(res.run_dir, "L001").revision == out.revision + 1
    assert review.fallback_line(res.run_dir, "L002", comp.bibles).lines[1].status == "fallback"


def test_regenerate_line_marks_repaired_and_uses_hint(tmp_path):
    comp, res = _parked(tmp_path)
    comp.client.responses["writer"] = [RepairDraft(text="He crosses the quiet hall alone", facts_used=["action"])]
    out = asyncio.run(review.regenerate_line(res.run_dir, "L002", "shorter please", comp.client, comp.scheduler,
                                             ArtifactCache(tmp_path / "cache"), comp.bibles))
    assert out.lines[1].status == "repaired" and out.lines[1].text == "He crosses the quiet hall alone"
    assert "shorter please" in comp.client.calls[-1][1]


def test_approve_applies_bible_once(tmp_path):
    comp, res = _parked(tmp_path)
    assert comp.bibles.load("test-series").version == 0
    bible = review.approve(res.run_dir, comp.bibles)
    assert bible.version == 1 and bible.plot_so_far == "Kai arrives in town."
    with pytest.raises(ValueError):
        review.approve(res.run_dir, comp.bibles)
    assert comp.bibles.load("test-series").version == 1
    assert json.loads((res.run_dir / "review.json").read_text(encoding="utf-8"))["status"] == "approved"


def _cli(tmp_path, monkeypatch, comp):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from engine.narration import __main__ as cli

    db = SimpleNamespace(query=lambda m: [SimpleNamespace(workspace_path=str(tmp_path / "ws"))])
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(cli, "BibleStore", lambda: comp.bibles)
    return cli


def test_cli_approve_prints_version(tmp_path, monkeypatch, capsys):
    comp, res = _parked(tmp_path)
    cli = _cli(tmp_path, monkeypatch, comp)
    assert cli.main(["review", "approve", str(res.run_dir)]) == 0
    assert capsys.readouterr().out.strip() == "bible version: 1"
    assert cli.main(["review", "approve", str(res.run_dir)]) == 1


def test_cli_rejects_run_dir_outside_workspaces(tmp_path, monkeypatch, capsys):
    import shutil

    comp, res = _parked(tmp_path)
    cli = _cli(tmp_path, monkeypatch, comp)
    outside = tmp_path / "elsewhere" / res.run_dir.name
    shutil.copytree(res.run_dir, outside)
    assert cli.main(["review", "approve", str(outside)]) == 1
    assert "not inside a known project workspace" in capsys.readouterr().out
    assert comp.bibles.load("test-series").version == 0


def test_item_must_name_its_own_run_dir(tmp_path):
    import shutil

    comp, res = _parked(tmp_path)
    copy = tmp_path / "copy"
    shutil.copytree(res.run_dir, copy)
    with pytest.raises(ValueError, match="does not belong"):
        review.approve(copy, comp.bibles)


def test_early_gate_run_gives_clear_errors(tmp_path):
    comp, res = _parked(tmp_path)
    (res.run_dir / "beat_sheet.json").unlink()
    with pytest.raises(ValueError, match="beat_sheet.json is missing"):
        review.fallback_line(res.run_dir, "L002", comp.bibles)
    (res.run_dir / "panel_facts.json").unlink()
    with pytest.raises(ValueError, match="panel_facts.json is missing"):
        review.edit_line(res.run_dir, "L002", "He walks on slowly now", comp.bibles)
    for f in res.run_dir.glob("script_r*.json"):
        f.unlink()
    with pytest.raises(ValueError, match="no script yet"):
        review.accept_line(res.run_dir, "L001")


def test_approved_run_is_frozen(tmp_path):
    comp, res = _parked(tmp_path)
    review.approve(res.run_dir, comp.bibles)
    for call in (lambda: review.edit_line(res.run_dir, "L002", "He walks on slowly now", comp.bibles),
                 lambda: review.accept_line(res.run_dir, "L002"),
                 lambda: review.fallback_line(res.run_dir, "L002", comp.bibles)):
        with pytest.raises(ValueError, match="frozen"):
            call()
    with pytest.raises(ValueError, match="frozen"):
        asyncio.run(review.regenerate_line(res.run_dir, "L002", "h", comp.client, comp.scheduler,
                                           ArtifactCache(tmp_path / "cache"), comp.bibles))


def test_list_pending_skips_corrupt_review_json(tmp_path):
    comp, res = _parked(tmp_path)
    bad = tmp_path / "ws" / "narration" / "bad"
    bad.mkdir()
    (bad / "review.json").write_text("{nope", encoding="utf-8")
    assert [i.run_id for i in review.list_pending(tmp_path)] == [res.run_id]


def test_edit_line_rejects_invented_name(tmp_path):
    comp, res = _parked(tmp_path)
    with pytest.raises(ValueError, match="unknown_name"):
        review.edit_line(res.run_dir, "L002", "He meets Zorg in the hall", comp.bibles)


def test_approve_rejects_unresolved_lines(tmp_path):
    comp, res = _parked(tmp_path)
    s = _script(res.run_dir)
    review._save(res.run_dir, review.revise(s, {"L001": dict(status="needs_review")}))
    with pytest.raises(ValueError, match="L001"):
        review.approve(res.run_dir, comp.bibles)


def test_fallback_line_refuses_blank_action(tmp_path):
    comp, res = _parked(tmp_path)
    p = res.run_dir / "panel_facts.json"
    rows = json.loads(p.read_text(encoding="utf-8"))
    rows[1]["action"] = " . "
    p.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="no action to fall back to"):
        review.fallback_line(res.run_dir, "L002", comp.bibles)


def test_regenerate_line_runs_rules(tmp_path):
    comp, res = _parked(tmp_path)
    comp.client.responses["writer"] = [RepairDraft(text="He meets Zorg in the hall", facts_used=["action"])]
    out = asyncio.run(review.regenerate_line(res.run_dir, "L002", "h", comp.client, comp.scheduler,
                                             ArtifactCache(tmp_path / "cache"), comp.bibles))
    assert out.lines[1].status == "needs_review" and out.lines[1].text == "He meets Zorg in the hall"
    crit = json.loads((res.run_dir / "critique.json").read_text(encoding="utf-8"))
    checks = next(lc for lc in crit["lines"] if lc["line_id"] == "L002")["checks"]
    assert any(c["rule"] == "unknown_name" and not c["passed"] and "Zorg" in c["reason"] for c in checks)
    with pytest.raises(ValueError, match="L002"):
        review.approve(res.run_dir, comp.bibles)
