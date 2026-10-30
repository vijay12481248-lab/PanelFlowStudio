"""Review queue: chapters parked at gate `review`, line actions that write new script revisions, approval."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from engine.narration.artifacts import (
    BeatSheet, CritiqueReport, PanelFacts, ReviewItem, ScriptIR, SeriesBible,
)
from engine.narration.bible.store import BibleStore, apply_once
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import _write_json
from engine.narration.runtime.client import ModelClient
from engine.narration.runtime.prompts import load_prompt
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps._cached import cached_call
from engine.narration.steps.critique.rules import rule_checks
from engine.narration.steps.factview import FACT_REF, char_names, normalize_facts, panel_line
from engine.narration.steps.repair import REPAIR_PROMPT_VERSION, REPAIR_STEP, RepairDraft, fallback_text, revise

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
    return _save(run_dir, new)


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
    names = char_names(bibles.load(_item(run_dir).series_key), _sheet(run_dir))
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
        panel=panel_line(1, facts[ln.panel_id], char_names(bible, sheet)),
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
        return _save(run_dir, new)
    # a block rule failed: keep the text for the reviewer, but never call it repaired; the reasons go into critique.json
    new = revise(script, {line_id: dict(text=new.lines[i].text, facts_used=used, status="needs_review")})
    fresh = {c.rule for c in checks}
    _write_json(run_dir / "critique.json", report.model_copy(update={"lines": [
        lc.model_copy(update={"checks": [*(c for c in lc.checks if c.rule not in fresh), *checks]})
        if lc.line_id == line_id else lc for lc in report.lines]}).model_dump(mode="json"))
    return _save(run_dir, new)


def approve(run_dir: Path, bibles: BibleStore) -> SeriesBible:
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
    return bibles.save(new, item.project_id, applied) if applied else bible
