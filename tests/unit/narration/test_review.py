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


def test_cli_approve_prints_version(tmp_path, monkeypatch, capsys):
    from engine.narration import __main__ as cli

    comp, res = _parked(tmp_path)
    monkeypatch.setattr(cli, "BibleStore", lambda: comp.bibles)
    assert cli.main(["review", "approve", str(res.run_dir)]) == 0
    assert capsys.readouterr().out.strip() == "bible version: 1"
    assert cli.main(["review", "approve", str(res.run_dir)]) == 1


def test_approve_rejects_unresolved_lines(tmp_path):
    comp, res = _parked(tmp_path)
    s = _script(res.run_dir)
    review._save(res.run_dir, review.revise(s, {"L001": dict(status="needs_review")}))
    with pytest.raises(ValueError, match="L001"):
        review.approve(res.run_dir, comp.bibles)
