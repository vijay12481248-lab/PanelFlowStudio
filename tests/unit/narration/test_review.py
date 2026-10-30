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
    bible = review.approve(res.run_dir, comp.bibles).bible
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

    async def fake_continue(project_id, run_id):
        assert (project_id, run_id) == ("proj-test", res.run_id)
        return "vs-1"

    monkeypatch.setattr(review, "continue_after_approval", fake_continue)
    assert cli.main(["review", "approve", str(res.run_dir)]) == 0
    assert capsys.readouterr().out.splitlines() == ["bible version: 1", "video script: vs-1"]
    assert cli.main(["review", "approve", str(res.run_dir)]) == 0  # stranded (no timeline yet): goes straight to continue
    assert capsys.readouterr().out.splitlines() == ["bible version: 1", "video script: vs-1"]
    (res.run_dir / "timeline.json").write_text("{}", encoding="utf-8")  # continue died after the timeline: still retried
    assert cli.main(["review", "approve", str(res.run_dir)]) == 0
    capsys.readouterr()
    (res.run_dir / "continued.json").write_text('"vs-1"', encoding="utf-8")
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


# ---- finishing an approved review (perform, voice, timeline, projection) ----
import time
import uuid

from engine.database.models import ProjectRecord, VideoScriptRecord
from engine.database.session import SessionLocal, init_db
from tests.unit.narration.test_compiler import _Echo
from tests.unit.narration.test_voice import FakeStt, FakeTts


def _adopt(tmp_path, comp, res, monkeypatch):
    """Give the parked run a real project row and make continue_after_approval use the fake compiler."""
    init_db()
    pid = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path / "ws")))
        db.commit()
    p = res.run_dir / "review.json"
    item = ReviewItem.model_validate_json(p.read_text(encoding="utf-8"))
    p.write_text(item.model_copy(update={"project_id": pid}).model_dump_json(), encoding="utf-8")

    async def build(workspace):
        return comp

    monkeypatch.setattr(review, "_build_compiler", build)
    return pid


def _park_at_critique(tmp_path, monkeypatch):
    tts = FakeTts()
    comp = _compiler(tmp_path, _write_responses(bad="number 2"), tts, _Echo(tts))
    res = _go(tmp_path, comp, stop_after="timeline")
    assert res.gate == "review" and not (res.run_dir / "takes.json").exists()
    return tts, comp, res, _adopt(tmp_path, comp, res, monkeypatch)


def _steps_of(run_dir):
    return [s["step"] for s in json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["steps"]]


def test_continue_after_critique_review_runs_perform_voice_timeline(tmp_path, monkeypatch):
    tts, comp, res, pid = _park_at_critique(tmp_path, monkeypatch)
    assert review.approve(res.run_dir, comp.bibles).needs_continue is True
    script_id = asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert _steps_of(res.run_dir)[-3:] == ["perform", "voice", "timeline"]
    assert _steps_of(res.run_dir)[:5] == ["perceive", "understand", "write", "critique", "repair"]
    for name in ("performance.json", "takes.json", "timeline.json", "sync.json"):
        assert (res.run_dir / name).exists()
    assert json.loads((res.run_dir / "continued.json").read_text(encoding="utf-8")) == script_id
    assert not (res.run_dir / "continue.lock").exists()
    with SessionLocal() as db:
        assert db.get(VideoScriptRecord, script_id).status == "APPROVED"
        assert len(db.get(ProjectRecord, pid).settings["story_editor_state"]["narration_clips"]) == 3
    assert comp.bibles.load("test-series").version == 1  # approve applied it; continue did not apply it again


def test_continue_after_voice_review_reuses_takes_unflagged(tmp_path, monkeypatch):
    tts = FakeTts()
    comp = _compiler(tmp_path, _write_responses(), tts, FakeStt(["zzz"]))
    res = _go(tmp_path, comp, stop_after="timeline")
    assert res.gate == "review" and any(t.flagged for t in res.takes)
    pid = _adopt(tmp_path, comp, res, monkeypatch)
    heard = len(tts.calls)
    assert review.approve(res.run_dir, comp.bibles).needs_continue is True
    script_id = asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert len(tts.calls) == heard  # not re-voiced
    takes = json.loads((res.run_dir / "takes.json").read_text(encoding="utf-8"))
    assert takes and not any(t["flagged"] for t in takes)
    assert (res.run_dir / "timeline.json").exists() and _steps_of(res.run_dir)[-1] == "timeline" and script_id


def test_continue_is_idempotent(tmp_path, monkeypatch):
    tts, comp, res, pid = _park_at_critique(tmp_path, monkeypatch)
    review.approve(res.run_dir, comp.bibles)
    first = asyncio.run(review.continue_after_approval(pid, res.run_id))
    calls, steps = len(tts.calls), _steps_of(res.run_dir)
    assert asyncio.run(review.continue_after_approval(pid, res.run_id)) == first
    assert len(tts.calls) == calls and _steps_of(res.run_dir) == steps
    with SessionLocal() as db:
        assert db.query(VideoScriptRecord).filter_by(project_id=pid).count() == 1


def test_concurrent_continue_rejected(tmp_path, monkeypatch):
    tts, comp, res, pid = _park_at_critique(tmp_path, monkeypatch)
    review.approve(res.run_dir, comp.bibles)
    (res.run_dir / "continue.lock").write_text(json.dumps({"created": time.time() - 60}), encoding="utf-8")
    with pytest.raises(ValueError, match="continue already running"):
        asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert (res.run_dir / "continue.lock").exists() and not tts.calls  # the other job's lock is left alone
    with SessionLocal() as db:
        assert db.query(VideoScriptRecord).filter_by(project_id=pid).count() == 0


def test_continue_refuses_unapproved_run(tmp_path, monkeypatch):
    tts, comp, res, pid = _park_at_critique(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not approved"):
        asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert not (res.run_dir / "continue.lock").exists()


def test_approve_reports_needs_continue(tmp_path):
    comp, res = _parked(tmp_path)
    assert review.approve(res.run_dir, comp.bibles).needs_continue is True
    (tmp_path / "again").mkdir()
    comp, res = _parked(tmp_path / "again")
    (res.run_dir / "timeline.json").write_text("{}", encoding="utf-8")
    assert review.approve(res.run_dir, comp.bibles).needs_continue is False


def test_resolve_run_dir_rejects_crafted_ids(tmp_path):
    init_db()
    pid = str(uuid.uuid4())
    good = "20261031T101500-abc123"
    (tmp_path / "narration" / good).mkdir(parents=True)
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.commit()
        assert review.resolve_run_dir(db, pid, good) == (tmp_path / "narration" / good).resolve()
        for bad in ("..\\..\\x", str(tmp_path), good + "\n", "20261031T101500-ABC123", "../" + good):
            with pytest.raises(ValueError):
                review.resolve_run_dir(db, pid, bad)
        with pytest.raises(FileNotFoundError):
            review.resolve_run_dir(db, pid, "20261031T101500-000000")
        with pytest.raises(KeyError):
            review.resolve_run_dir(db, "nope", good)


def test_edited_line_is_revoiced_and_heard_lines_are_unflagged(tmp_path, monkeypatch):
    tts = FakeTts()
    comp = _compiler(tmp_path, _write_responses(), tts, FakeStt(["zzz"]))
    res = _go(tmp_path, comp, stop_after="timeline")
    assert res.gate == "review"
    pid = _adopt(tmp_path, comp, res, monkeypatch)
    review.edit_line(res.run_dir, "L002", "He walks through the quiet hall slowly", comp.bibles)
    comp.stt = _Echo(tts)  # the new take hears itself, so it passes
    heard = len(tts.calls)
    review.approve(res.run_dir, comp.bibles)
    asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert len(tts.calls) == heard + 1 and tts.calls[-1][0].startswith("He walks through")
    takes = json.loads((res.run_dir / "takes.json").read_text(encoding="utf-8"))
    assert [t["flagged"] for t in takes] == [False, False, False]


def test_edited_line_that_fails_the_speech_check_keeps_its_flag(tmp_path, monkeypatch):
    tts = FakeTts()
    comp = _compiler(tmp_path, _write_responses(), tts, FakeStt(["zzz"]))
    res = _go(tmp_path, comp, stop_after="timeline")
    pid = _adopt(tmp_path, comp, res, monkeypatch)
    review.edit_line(res.run_dir, "L002", "He walks through the quiet hall slowly", comp.bibles)
    review.approve(res.run_dir, comp.bibles)
    with pytest.raises(ValueError, match="failed the speech check"):  # 1 of 3 flagged is over the limit: parked again
        asyncio.run(review.continue_after_approval(pid, res.run_id))
    takes = {t["line_id"]: t for t in json.loads((res.run_dir / "takes.json").read_text(encoding="utf-8"))}
    assert [takes[k]["flagged"] for k in ("L001", "L002", "L003")] == [False, True, False]
    assert json.loads((res.run_dir / "review.json").read_text(encoding="utf-8"))["status"] == "pending"


def test_stale_continue_lock_is_replaced(tmp_path, monkeypatch):
    tts, comp, res, pid = _park_at_critique(tmp_path, monkeypatch)
    review.approve(res.run_dir, comp.bibles)
    (res.run_dir / "continue.lock").write_text(
        json.dumps({"created": time.time() - review.LOCK_TTL - 5}), encoding="utf-8")
    assert asyncio.run(review.continue_after_approval(pid, res.run_id))
    assert not (res.run_dir / "continue.lock").exists()
