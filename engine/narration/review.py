"""Review queue: chapters parked at gate `review`, line actions that write new script revisions, approval."""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Literal, NamedTuple

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, PanelFacts, ReviewItem, ScriptIR, SeriesBible,
)
from engine.narration.bible.store import BibleStore, apply_once
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import _write_json
from engine.database.models import ProjectRecord
from engine.database.session import SessionLocal
from engine.narration.inputs import ChapterInputs
from engine.narration.learning import record_pair
from engine.narration.project import apply_to_project
from engine.narration.runtime.client import ModelClient
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.rules import rule_checks
from engine.narration.steps.factview import FACT_REF, beat_context, char_names, cues_of, normalize_facts, panel_line
from engine.narration.steps.repair import REPAIR_PROMPT_VERSION, REPAIR_STEP, RepairDraft, fallback_text, revise
from engine.security.paths import resolve_contained_path

_OK = {"passed", "repaired", "fallback"}


__all__ = ["ReviewItem"]  # re-export: defined in artifacts to keep the compiler import acyclic


def _item(run_dir: Path) -> ReviewItem:
    item = ReviewItem.model_validate_json((run_dir / "review.json").read_text(encoding="utf-8"))
    if Path(item.run_dir).resolve() != Path(run_dir).resolve():
        raise ValueError("review.json does not belong to this run directory")
    return item


def _open(run_dir: Path) -> ReviewItem:
    item = _item(run_dir)
    if item.status == "approved":
        raise ValueError("run is approved and frozen")
    return item


def list_pending(projects_root: Path) -> list[ReviewItem]:
    items = []
    for p in sorted(Path(projects_root).glob("*/narration/*/review.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            items.append(ReviewItem.model_validate_json(p.read_text(encoding="utf-8")))
        except ValueError:  # one corrupt file must not hide the rest
            continue
    return [i for i in items if i.status == "pending"]


def _latest(run_dir: Path) -> ScriptIR:
    revs = [(int(m.group(1)), p) for p in run_dir.glob("script_r*.json") if (m := re.fullmatch(r"script_r(\d+)\.json", p.name))]
    if not revs:
        raise ValueError("no script yet; this run stopped before write")
    return ScriptIR.model_validate_json(max(revs)[1].read_text(encoding="utf-8"))


def _save(run_dir: Path, script: ScriptIR) -> ScriptIR:
    payload = script.model_dump(mode="json")
    _write_json(run_dir / f"script_r{script.revision}.json", payload)
    _write_json(run_dir / "script.json", payload)
    return script


def _read(run_dir: Path, name: str) -> str:
    try:
        return (run_dir / name).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"{name} is missing; this run stopped before it was written") from None


def _facts(run_dir: Path) -> dict[str, PanelFacts]:
    import json
    raw = json.loads(_read(run_dir, "panel_facts.json"))
    return {f["panel_id"]: PanelFacts.model_validate(f) for f in raw}


def _sheet(run_dir: Path) -> BeatSheet:
    return BeatSheet.model_validate_json(_read(run_dir, "beat_sheet.json"))


def _line(script: ScriptIR, line_id: str):
    for ln in script.lines:
        if ln.line_id == line_id:
            return ln
    raise ValueError(f"unknown line: {line_id}")


def _pair_facts(run_dir: Path, facts: dict[str, PanelFacts], line_id: str, script: ScriptIR, bibles: BibleStore) -> str:
    names = char_names(bibles.load(_item(run_dir).series_key), _sheet(run_dir), cues_of(facts.values()))
    return panel_line(1, facts[_line(script, line_id).panel_id], names).split(" | ", 1)[1]  # few-shot rows carry no P<k> prefix


def edit_line(run_dir: Path, line_id: str, text: str, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    _open(run_dir)
    script = _latest(run_dir)
    _line(script, line_id)
    facts = _facts(run_dir)
    new = revise(script, {line_id: dict(text=" ".join(text.split()), status="passed")})
    story = [ln.panel_id for ln in new.lines]
    checks = rule_checks(new, facts, story, bibles.load(_item(run_dir).series_key))[line_id]
    failed = [f"{c.rule}: {c.reason}" for c in checks if not c.passed and c.severity == "block"]
    if failed:
        raise ValueError("; ".join(failed))
    pair = ("edit", _line(script, line_id).text, _line(new, line_id).text, _pair_facts(run_dir, facts, line_id, script, bibles), [])
    _save(run_dir, new)
    record_pair(*pair, _item(run_dir).series_key)  # only a saved edit is a preference
    return new


def accept_line(run_dir: Path, line_id: str) -> ScriptIR:
    _open(Path(run_dir))
    script = _latest(Path(run_dir))
    _line(script, line_id)
    return _save(Path(run_dir), revise(script, {line_id: dict(status="passed")}))


def fallback_line(run_dir: Path, line_id: str, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    _open(run_dir)
    script = _latest(run_dir)
    ln = _line(script, line_id)
    names = char_names(bibles.load(_item(run_dir).series_key), _sheet(run_dir), cues_of(_facts(run_dir).values()))
    return _save(run_dir, revise(script, {line_id: dict(
        text=fallback_text(_facts(run_dir)[ln.panel_id], names), facts_used=["action", "characters"], status="fallback")}))


async def regenerate_line(run_dir: Path, line_id: str, hint: str, client: ModelClient, scheduler: ModelScheduler,
                          cache: ArtifactCache, bibles: BibleStore | None = None) -> ScriptIR:
    run_dir, bibles = Path(run_dir), bibles or BibleStore()
    item = _open(run_dir)
    script, facts, sheet = _latest(run_dir), _facts(run_dir), _sheet(run_dir)
    bible = bibles.load(item.series_key)
    at = {ln.line_id: i for i, ln in enumerate(script.lines)}
    if line_id not in at:
        raise ValueError(f"unknown line: {line_id}")
    i, ln = at[line_id], script.lines[at[line_id]]
    report = CritiqueReport.model_validate_json((run_dir / "critique.json").read_text(encoding="utf-8"))
    failures = [f"- {c.rule}: {c.reason}" for lc in report.lines if lc.line_id == line_id
                for c in lc.checks if not c.passed and c.severity == "block"]
    voice, prompt = bible.narrator_voice, load_prompt(REPAIR_STEP, REPAIR_PROMPT_VERSION)
    text = prompt.render(
        failures="\n".join([*failures, f"- reviewer hint: {hint}"]), line=ln.text,
        panel=panel_line(1, facts[ln.panel_id], char_names(bible, sheet, cues_of(facts.values()))),
        story=beat_context(sheet, ln.panel_id),
        previous=script.lines[i - 1].text if i else "(none)",
        next=script.lines[i + 1].text if i + 1 < len(script.lines) else "(none)",
        banned=", ".join(voice.banned_phrases) or "(none)", style="; ".join(voice.style_notes) or "plain, vivid recap voice")

    async def one(t: str) -> RepairDraft:
        return await cached_call(client, cache, "writer", REPAIR_STEP, prompt.sha256, t, RepairDraft)

    try:
        (draft,) = await scheduler.map("writer", [text], one)
    finally:
        await scheduler.release()
    used = [x for x in normalize_facts(draft.facts_used) if FACT_REF.match(x)] or ln.facts_used
    new = revise(script, {line_id: dict(text=" ".join(draft.text.split()), facts_used=used, status="repaired")})
    checks = rule_checks(new, facts, [x.panel_id for x in new.lines], bible)[line_id]
    if not any(not c.passed and c.severity == "block" for c in checks):
        pair = ("regenerate", ln.text, new.lines[i].text, _pair_facts(run_dir, facts, line_id, script, bibles), failures)
        _save(run_dir, new)
        record_pair(*pair, item.series_key)
        return new
    # a block rule failed: keep the text for the reviewer, but never call it repaired; the reasons go into critique.json
    new = revise(script, {line_id: dict(text=new.lines[i].text, facts_used=used, status="needs_review")})
    fresh = {c.rule for c in checks}
    _write_json(run_dir / "critique.json", report.model_copy(update={"lines": [
        lc.model_copy(update={"checks": [*(c for c in lc.checks if c.rule not in fresh), *checks]})
        if lc.line_id == line_id else lc for lc in report.lines]}).model_dump(mode="json"))
    return _save(run_dir, new)


class Approval(NamedTuple):
    bible: SeriesBible
    needs_continue: bool  # False when the run already has its locked timeline


def approve(run_dir: Path, bibles: BibleStore) -> Approval:
    run_dir = Path(run_dir)
    item = _open(run_dir)
    script = _latest(run_dir)
    open_ = [ln.line_id for ln in script.lines if ln.status not in _OK]
    if open_:
        raise ValueError(f"lines still need review: {', '.join(open_)}")
    bible = bibles.load(item.series_key)
    new, applied = apply_once(bible, _sheet(run_dir).bible_proposals, item.project_id)
    # approved first: a crash after this can never re-apply the proposals
    _write_json(run_dir / "review.json", item.model_copy(update={"status": "approved"}).model_dump(mode="json"))
    bible = bibles.save(new, item.project_id, applied) if applied else bible
    return Approval(bible, not (run_dir / "timeline.json").exists())


_RUN_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{6}")


def resolve_run_dir(db, project_id: str, run_id: str) -> Path:
    """The only way a request reaches a run: <workspace>/narration/<run_id>, never a client path."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise KeyError(project_id)
    run_dir = resolve_contained_path(Path(project.workspace_path), Path("narration") / run_id)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_id)
    return run_dir


LOCK_TTL = 2 * 3600  # a continue job that died leaves its lock behind; after this it is replaced


def _take_lock(path: Path) -> None:
    for _ in range(2):
        try:
            with open(path, "x") as f:
                f.write(json.dumps({"created": time.time()}))
            return
        except FileExistsError:
            try:
                created = json.loads(path.read_text(encoding="utf-8"))["created"]
            except (ValueError, KeyError, TypeError, OSError):
                created = path.stat().st_mtime if path.exists() else 0  # unreadable lock: its file time stands in
            if time.time() - created <= LOCK_TTL:
                break
            path.unlink(missing_ok=True)
    raise ValueError("continue already running")


async def _build_compiler(workspace: Path):  # tests replace this with a fake-model compiler
    from engine.narration.__main__ import _local_provider, _make_compiler

    provider = await _local_provider()
    if provider is None:
        raise RuntimeError("Ollama is not reachable")
    return _make_compiler(provider, workspace / "narration" / "cache", BibleStore())


async def continue_after_approval(project_id: str, run_id: str) -> str:
    """Finish an approved run (perform, voice, timeline, projection) once; returns the VideoScript id."""
    with SessionLocal() as db:
        run_dir = resolve_run_dir(db, project_id, run_id)
        workspace = Path(db.get(ProjectRecord, project_id).workspace_path)
    done = run_dir / "continued.json"
    if done.exists():
        return json.loads(done.read_text(encoding="utf-8"))
    item = _item(run_dir)
    if item.project_id != project_id:
        raise ValueError("run belongs to another project")
    if item.status != "approved":
        raise ValueError("run is not approved")
    _take_lock(run_dir / "continue.lock")
    try:
        if done.exists():  # a concurrent call finished between the first check and the lock
            return json.loads(done.read_text(encoding="utf-8"))
        compiler = await _build_compiler(workspace)
        res = await compiler.continue_run(run_dir, ChapterInputs(project_id, item.series_key, []), workspace)
        if res.gate != "pass":
            raise ValueError("; ".join(res.reasons) or f"continue ended with gate {res.gate}")
        with SessionLocal() as db:
            script_id = apply_to_project(db, project_id, res.timeline, res.script, res.beat_sheet, res.takes,
                                         workspace, res.plan)
        _write_json(done, script_id)
        return script_id
    finally:
        (run_dir / "continue.lock").unlink(missing_ok=True)
